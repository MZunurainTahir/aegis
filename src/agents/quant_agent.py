import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from src.config import DEFAULT_WATCHLIST, RISK_RULES
from src.alpaca_client.alpaca_service import alpaca_service, parse_option_symbol
from src.persistence.database import journal

logger = logging.getLogger("Aegis.QuantAgent")


class QuantAgent:
    """
    Quant Agent screens market data across the designated watchlist,
    identifies premium harvesting opportunities via the Options Wheel,
    and proposes structured trade tickets.

    v2.0 upgrades:
    - DUPLICATE GUARD: never stacks a second short put (or call) on a ticker
      that already has an open short option — the classic blow-up bug in
      naive auto-trading loops
    - CASH-AWARE SIZING: collateral checked against live cash minus reserve
    - IV RANK SCORING: candidates in high implied volatility get a yield boost
    - Earnings-blackout respect: skip tickers flagged by the News Agent
    """
    def __init__(self, watchlist: Optional[List[str]] = None):
        self.watchlist = watchlist or DEFAULT_WATCHLIST
        self.alpaca = alpaca_service
        self.journal = journal

    def screen_opportunities(self, exclude_tickers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Screens universe for Wheel opportunities:
        1. If holding >= 100 shares without short call -> Propose Covered Call (0.20-0.35 delta, 7-45 DTE, strike > cost basis).
        2. If cash available and no active short put -> Propose Cash-Secured Put (0.15-0.30 delta, 7-45 DTE).
        3. Scoring: annualized yield adjusted by IV-rank percentile of the contract.
        """
        proposals = []
        exclude = set(exclude_tickers or [])
        positions = self.alpaca.get_positions()

        # Map: ticker -> {shares, has_short_put, has_short_call}
        pos_state: Dict[str, Dict[str, Any]] = {}
        for p in positions:
            parsed = parse_option_symbol(p["symbol"])
            if parsed:
                und = parsed["underlying"]
                st = pos_state.setdefault(und, {"shares": 0, "has_short_put": False, "has_short_call": False, "cost_basis": 0.0})
                if p["qty"] < 0:
                    if parsed["option_type"] == "put":
                        st["has_short_put"] = True
                    else:
                        st["has_short_call"] = True
            else:
                st = pos_state.setdefault(p["symbol"], {"shares": 0, "has_short_put": False, "has_short_call": False, "cost_basis": 0.0})
                st["shares"] += p["qty"]
                if p["qty"] > 0:
                    st["cost_basis"] = abs(p["cost_basis"]) / max(1.0, p["qty"])

        account = self.alpaca.get_account_summary()
        equity = account.get("equity", 100000.0)
        cash = account.get("cash", 100000.0)
        min_reserve = equity * RISK_RULES.get("MIN_CASH_RESERVE_PCT", 0.05)
        deployable_cash = max(0.0, cash - min_reserve)

        for ticker in self.watchlist:
            if ticker in exclude:
                continue
            spot = self.alpaca.get_spot_price(ticker)
            chain = self.alpaca.get_option_chain_contracts(ticker)

            if not chain:
                continue

            state = pos_state.get(ticker, {"shares": 0, "has_short_put": False, "has_short_call": False, "cost_basis": 0.0})

            # --- Covered Call: hold 100+ shares, no existing short call ---
            if state["shares"] >= 100 and not state["has_short_call"]:
                cc_candidate = self._find_covered_call_candidate(ticker, spot, chain, state["cost_basis"] or spot)
                if cc_candidate:
                    cc_candidate["within_buying_power"] = True
                    proposals.append(cc_candidate)

            # --- Cash-Secured Put: no existing short put on this ticker ---
            elif not state["has_short_put"]:
                csp_candidate = self._find_csp_candidate(ticker, spot, chain)
                if csp_candidate:
                    within = csp_candidate["collateral_required"] <= deployable_cash
                    csp_candidate["within_buying_power"] = within
                    if within:
                        proposals.append(csp_candidate)
                    else:
                        logger.info(f"Skipping {ticker} CSP: collateral ${csp_candidate['collateral_required']:,.0f} exceeds deployable cash ${deployable_cash:,.0f}")

        # Sort: highest IV-adjusted score first
        proposals.sort(key=lambda x: x.get("iv_adjusted_score", x.get("annualized_yield", 0)), reverse=True)
        return proposals

    def _find_csp_candidate(self, ticker: str, spot: float, chain: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Finds the optimal Cash-Secured Put (0.15 - 0.30 delta, 7-45 DTE)."""
        valid_puts = [
            c for c in chain
            if c["option_type"] == "put"
            and RISK_RULES["TARGET_DTE_MIN"] <= c["dte"] <= RISK_RULES["TARGET_DTE_MAX"]
            and RISK_RULES["PUT_TARGET_DELTA_MIN"] <= abs(c["delta"]) <= RISK_RULES["PUT_TARGET_DELTA_MAX"]
            and c["strike"] < spot
            and c.get("mid", 0) > 0.05
        ]

        if not valid_puts:
            # Fallback to closest put in DTE window
            valid_puts = [
                c for c in chain
                if c["option_type"] == "put" and c["strike"] < spot and c.get("mid", 0) > 0.05
                and RISK_RULES["TARGET_DTE_MIN"] <= c["dte"] <= RISK_RULES["TARGET_DTE_MAX"]
            ]

        if not valid_puts:
            return None

        # IV rank percentile within this chain for premium-selling edge
        all_ivs = sorted(c.get("implied_volatility", 20) for c in chain if c.get("implied_volatility"))
        iv_rank = self._iv_percentile(valid_puts[0].get("implied_volatility", 20), all_ivs)

        # Pick candidate with best IV-adjusted premium yield
        best = max(valid_puts, key=lambda c: (c["mid"] / c["strike"]) if c["strike"] > 0 else 0)

        # Annualized Yield = (Premium / Strike) * (365 / DTE) * 100
        ann_yield = round((best["mid"] / best["strike"]) * (365.0 / max(1, best["dte"])) * 100, 2)
        collateral = best["strike"] * 100.0
        iv_bonus = 1.0 + (iv_rank / 100.0) * 0.5  # up to +50% score in top-percentile IV

        return {
            "strategy": "CASH_SECURED_PUT",
            "ticker": ticker,
            "contract_symbol": best["symbol"],
            "spot_price": spot,
            "strike": best["strike"],
            "expiration": best["expiration"],
            "dte": best["dte"],
            "delta": best["delta"],
            "theta": best["theta"],
            "vega": best["vega"],
            "bid": best["bid"],
            "ask": best["ask"],
            "estimated_premium": best["mid"],
            "total_credit": round(best["mid"] * 100.0, 2),
            "collateral_required": collateral,
            "annualized_yield": ann_yield,
            "iv_rank": round(iv_rank, 1),
            "iv_adjusted_score": round(ann_yield * iv_bonus, 2),
            "confidence_score": 88,
            "agent_thesis": f"Sell 1x OTM Put at {best['strike']} strike ({best['dte']} DTE, {best['delta']} delta). Implied volatility provides {ann_yield}% annualized yield (IV rank {round(iv_rank)}) with margin of safety {round((1 - best['strike']/spot)*100, 1)}% below spot."
        }

    def _find_covered_call_candidate(self, ticker: str, spot: float, chain: List[Dict[str, Any]], cost_basis: float) -> Optional[Dict[str, Any]]:
        """Finds the optimal Covered Call against held stock."""
        valid_calls = [
            c for c in chain
            if c["option_type"] == "call"
            and RISK_RULES["TARGET_DTE_MIN"] <= c["dte"] <= RISK_RULES["TARGET_DTE_MAX"]
            and RISK_RULES["CALL_TARGET_DELTA_MIN"] <= c["delta"] <= RISK_RULES["CALL_TARGET_DELTA_MAX"]
            and c["strike"] >= max(cost_basis, spot * 0.99)
            and c.get("mid", 0) > 0.05
        ]

        if not valid_calls:
            valid_calls = [
                c for c in chain
                if c["option_type"] == "call" and c["strike"] >= spot and c.get("mid", 0) > 0.05
                and RISK_RULES["TARGET_DTE_MIN"] <= c["dte"] <= RISK_RULES["TARGET_DTE_MAX"]
            ]

        if not valid_calls:
            return None

        best = max(valid_calls, key=lambda c: c["mid"])
        ann_yield = round((best["mid"] / spot) * (365.0 / max(1, best["dte"])) * 100, 2)

        all_ivs = sorted(c.get("implied_volatility", 20) for c in chain if c.get("implied_volatility"))
        iv_rank = self._iv_percentile(best.get("implied_volatility", 20), all_ivs)

        return {
            "strategy": "COVERED_CALL",
            "ticker": ticker,
            "contract_symbol": best["symbol"],
            "spot_price": spot,
            "strike": best["strike"],
            "expiration": best["expiration"],
            "dte": best["dte"],
            "delta": best["delta"],
            "theta": best["theta"],
            "vega": best["vega"],
            "bid": best["bid"],
            "ask": best["ask"],
            "estimated_premium": best["mid"],
            "total_credit": round(best["mid"] * 100.0, 2),
            "collateral_required": 0.0, # Covered by shares
            "annualized_yield": ann_yield,
            "iv_rank": round(iv_rank, 1),
            "iv_adjusted_score": round(ann_yield * (1.0 + (iv_rank / 100.0) * 0.5), 2),
            "confidence_score": 92,
            "agent_thesis": f"Sell 1x OTM Covered Call at {best['strike']} strike against 100 shares held (cost basis ${cost_basis:.2f}). Captures ${best['mid']*100:.2f} theta income ({ann_yield}% annualized)."
        }

    @staticmethod
    def _iv_percentile(iv: float, sorted_ivs: List[float]) -> float:
        """Percentile rank of an IV within the chain's IV distribution (0-100)."""
        if not sorted_ivs:
            return 50.0
        below = sum(1 for x in sorted_ivs if x <= iv)
        return round(below / len(sorted_ivs) * 100.0, 1)


quant_agent = QuantAgent()
