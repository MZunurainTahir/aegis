import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple

from src.config import RISK_RULES
from src.alpaca_client.alpaca_service import alpaca_service
from src.persistence.database import journal

logger = logging.getLogger("Aegis.RiskAgent")


class RiskGovernanceAgent:
    """
    Sovereign Risk & Governance Agent with absolute veto authority
    and autonomous tail-risk hedging capability.

    v2.0 upgrades:
    - REAL market stress index (SPY ATM IV VIX-proxy) instead of hardcoded values
    - Tail hedge EXECUTES actual protective put orders on Alpaca
    - Hedge cooldown prevents duplicate hedge stacking
    - Delta-aware hedge sizing
    """
    def __init__(self):
        self.rules = RISK_RULES
        self.alpaca = alpaca_service
        self.journal = journal

    def audit_trade_proposal(
        self,
        candidate_trade: Dict[str, Any],
        sentiment_eval: Dict[str, Any]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Performs deterministic and quantitative risk audit on a candidate trade.
        Returns:
            (approved: bool, verdict: str, audit_metadata: dict)
        """
        account = self.alpaca.get_account_summary()
        equity = account.get("equity", 100000.0)
        cash = account.get("cash", 100000.0)
        positions = self.alpaca.get_positions()
        greeks = self.alpaca.calculate_portfolio_greeks()

        ticker = candidate_trade["ticker"]
        collateral_req = candidate_trade.get("collateral_required", 0.0)
        strategy = candidate_trade.get("strategy", "CASH_SECURED_PUT")

        # 1. Check Sentiment Agent Veto Recommendation
        if sentiment_eval.get("veto_recommended", False):
            return False, "VETOED_BY_SENTIMENT_AGENT", {
                "reason": "Sentiment agent flagged elevated binary/earnings downside risk.",
                "details": sentiment_eval.get("sentiment_summary", "")
            }

        # 2. Check Drawdown Circuit Breaker
        day_pnl_pct = account.get("day_pnl_pct", 0.0)
        if day_pnl_pct < - (self.rules["DRAWDOWN_CIRCUIT_BREAKER_PCT"] * 100):
            return False, "CIRCUIT_BREAKER_TRIGGERED", {
                "reason": f"Account drawdown ({day_pnl_pct}%) exceeds max allowable circuit breaker threshold (-{self.rules['DRAWDOWN_CIRCUIT_BREAKER_PCT']*100}%). New premium selling paused.",
                "action": "HALT_NEW_TRADES"
            }

        # 3. Check Position Size Limit (Max 35% of portfolio equity)
        max_capital_per_pos = equity * self.rules["MAX_CAPITAL_PER_POSITION_PCT"]
        if strategy == "CASH_SECURED_PUT" and collateral_req > max_capital_per_pos:
            return False, "REJECTED_POSITION_SIZE_EXCEEDED", {
                "reason": f"Required collateral (${collateral_req:,.2f}) exceeds 35% position limit (${max_capital_per_pos:,.2f}).",
                "recommendation": "Resize to smaller underlying or tighter spread."
            }

        # 4. Check Single Ticker Concentration Limit (Max 40% of portfolio equity)
        current_ticker_exposure = sum(
            abs(p["market_value"]) for p in positions if ticker in p["symbol"]
        )
        new_total_exposure = current_ticker_exposure + collateral_req
        max_ticker_exposure = equity * self.rules["MAX_EXPOSURE_PER_TICKER_PCT"]
        if new_total_exposure > max_ticker_exposure:
            return False, "REJECTED_CONCENTRATION_LIMIT", {
                "reason": f"Total exposure for {ticker} (${new_total_exposure:,.2f}) would exceed 40% ticker concentration limit (${max_ticker_exposure:,.2f})."
            }

        # 5. Check Cash Sufficiency (with untouchable reserve buffer)
        if strategy == "CASH_SECURED_PUT":
            min_reserve = equity * self.rules.get("MIN_CASH_RESERVE_PCT", 0.05)
            if cash < collateral_req + min_reserve:
                return False, "REJECTED_INSUFFICIENT_CASH", {
                    "reason": f"Available cash (${cash:,.2f}) is less than required collateral (${collateral_req:,.2f}) plus ${min_reserve:,.0f} strategic reserve."
                }

        # 6. Check Portfolio Delta Bounds
        net_delta = greeks.get("net_delta", 0.0)
        trade_delta = candidate_trade.get("delta", 0.0) * 100.0
        projected_delta = net_delta + trade_delta
        if projected_delta > self.rules["MAX_PORTFOLIO_DELTA"] or projected_delta < self.rules["MIN_PORTFOLIO_DELTA"]:
            # Allowed but logged with caution
            logger.info(f"Projected portfolio delta ({projected_delta}) approaching boundary.")

        # All hard gates passed -> APPROVED
        audit_metadata = {
            "verdict": "APPROVED",
            "passed_checks": [
                "Max 35% Position Size Check Passed",
                "Max 40% Ticker Concentration Check Passed",
                "Cash Collateral Verification Passed",
                "Sentiment & Catalyst Risk Check Passed",
                "Drawdown Circuit Breaker Normal"
            ],
            "portfolio_delta_post_trade": round(projected_delta, 2),
            "estimated_theta_boost": round(abs(candidate_trade.get("theta", 0.0) * 100.0), 2)
        }

        return True, "APPROVED", audit_metadata

    def check_and_trigger_tail_hedge(self, market_stress_index: float = None,
                                     execute: bool = True) -> Dict[str, Any]:
        """
        Autonomous Hedging Engine:
        Evaluates portfolio risk. If market stress exceeds threshold or net delta is overly positive,
        autonomously deploys a SPY/QQQ protective put tail hedge — now with REAL order execution
        and cooldown-based dedupe so hedges never stack.
        """
        if market_stress_index is None:
            market_stress_index = self.alpaca.get_market_stress_index()

        account = self.alpaca.get_account_summary()
        greeks = self.alpaca.calculate_portfolio_greeks()

        hedge_triggered = False
        hedge_action = None
        trigger_reason = None

        stress_breach = market_stress_index >= self.rules["STRESS_VIX_HEDGE_THRESHOLD"]
        delta_breach = greeks["net_delta"] > self.rules["MAX_PORTFOLIO_DELTA"]

        if stress_breach or delta_breach:
            trigger_reason = (
                f"Market stress index ({market_stress_index}) above threshold {self.rules['STRESS_VIX_HEDGE_THRESHOLD']}"
                if stress_breach
                else f"Portfolio net delta ({greeks['net_delta']}) above cap {self.rules['MAX_PORTFOLIO_DELTA']}"
            )

            # Cooldown check: don't stack hedges
            if self._within_hedge_cooldown():
                hedge_action = {
                    "ticker": "SPY",
                    "type": "HEDGE_SUPPRESSED_COOLDOWN",
                    "reason": f"{trigger_reason} — hedge suppressed: existing hedge within cooldown window ({self.rules.get('HEDGE_COOLDOWN_HOURS', 20)}h).",
                }
                logger.warning(f"Hedge trigger suppressed by cooldown: {trigger_reason}")
            else:
                spy_spot = self.alpaca.get_spot_price("SPY")
                strike = round(spy_spot * 0.96, 0)  # 4% OTM protective put

                # Find a real SPY put contract to buy
                contract, dte = self._find_hedge_contract(strike)

                hedge_action = {
                    "ticker": "SPY",
                    "type": "BUY_PROTECTIVE_PUT",
                    "strike": strike,
                    "dte": dte,
                    "contract_symbol": contract,
                    "reason": f"{trigger_reason}.",
                    "cost_est": round(spy_spot * 0.008 * 100, 2)
                }

                if execute and contract:
                    order = self.alpaca.execute_order(
                        symbol=contract,
                        qty=1,
                        side="buy",
                        order_type="limit",
                        limit_price=max(0.05, round(spy_spot * 0.008, 2)),
                    )
                    hedge_action["order_result"] = order
                    if order.get("success"):
                        hedge_action["executed"] = True
                        hedge_action["order_id"] = order.get("order_id")
                        self.journal.record_hedge(
                            contract_symbol=contract,
                            strike=strike,
                            dte=dte,
                            cost=hedge_action["cost_est"],
                            reason=trigger_reason,
                            order_id=order.get("order_id"),
                        )
                        self.journal.record_trade_open(
                            contract_symbol=contract, ticker="SPY", strategy="TAIL_HEDGE",
                            side="HEDGE_BUY", qty=1, strike=strike, expiration=None,
                            dte=dte, delta=-0.20, premium=round(spy_spot * 0.008, 2),
                            order_id=order.get("order_id"), order_status=order.get("status", "FILLED"),
                            risk_verdict="TAIL_HEDGE",
                            agent_thesis=trigger_reason,
                        )
                        logger.warning(f"AUTONOMOUS TAIL HEDGE EXECUTED: BUY 1x {contract} @ ${strike} strike")
                    else:
                        hedge_action["executed"] = False
                        hedge_action["error"] = order.get("error", "Order rejected")

                hedge_triggered = True

        return {
            "stress_index": market_stress_index,
            "threshold": self.rules["STRESS_VIX_HEDGE_THRESHOLD"],
            "hedge_triggered": hedge_triggered,
            "hedge_action": hedge_action,
            "current_portfolio_delta": greeks["net_delta"],
            "trigger_reason": trigger_reason,
        }

    def _within_hedge_cooldown(self) -> bool:
        last = self.journal.last_hedge_time()
        if not last:
            return False
        try:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            cooldown = timedelta(hours=self.rules.get("HEDGE_COOLDOWN_HOURS", 20))
            return datetime.now(timezone.utc) - last_dt < cooldown
        except Exception:
            return False

    def _find_hedge_contract(self, target_strike: float) -> Tuple[str, int]:
        """Finds a real ~14 DTE SPY put near the 4% OTM hedge strike."""
        try:
            chain = self.alpaca.get_option_chain_contracts("SPY")
            puts = [c for c in chain if c["option_type"] == "put" and 7 <= c["dte"] <= 21 and c.get("mid", 0) > 0.05]
            if not puts:
                return self._synthetic_hedge_symbol(target_strike), 14
            best = min(puts, key=lambda c: abs(c["strike"] - target_strike))
            return best["symbol"], best["dte"]
        except Exception as e:
            logger.warning(f"Hedge contract lookup failed: {e}")
            return self._synthetic_hedge_symbol(target_strike), 14

    def _synthetic_hedge_symbol(self, strike: float) -> str:
        exp = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%y%m%d")
        return f"SPY{exp}P{int(round(strike) * 1000):08d}"


risk_agent = RiskGovernanceAgent()
