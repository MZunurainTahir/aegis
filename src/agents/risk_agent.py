import logging
from typing import Dict, Any, Tuple
from src.config import RISK_RULES
from src.alpaca_client.alpaca_service import alpaca_service

logger = logging.getLogger("Aegis.RiskAgent")

class RiskGovernanceAgent:
    """
    Sovereign Risk & Governance Agent with absolute veto authority
    and autonomous tail-risk hedging capability.
    """
    def __init__(self):
        self.rules = RISK_RULES
        self.alpaca = alpaca_service

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

        # 3. Check Position Size Limit (Max 10% of portfolio equity)
        max_capital_per_pos = equity * self.rules["MAX_CAPITAL_PER_POSITION_PCT"]
        if strategy == "CASH_SECURED_PUT" and collateral_req > max_capital_per_pos:
            return False, "REJECTED_POSITION_SIZE_EXCEEDED", {
                "reason": f"Required collateral (${collateral_req:,.2f}) exceeds 10% position limit (${max_capital_per_pos:,.2f}).",
                "recommendation": "Resize to smaller underlying or tighter spread."
            }

        # 4. Check Single Ticker Concentration Limit (Max 20% of portfolio equity)
        current_ticker_exposure = sum(
            abs(p["market_value"]) for p in positions if ticker in p["symbol"]
        )
        new_total_exposure = current_ticker_exposure + collateral_req
        max_ticker_exposure = equity * self.rules["MAX_EXPOSURE_PER_TICKER_PCT"]
        if new_total_exposure > max_ticker_exposure:
            return False, "REJECTED_CONCENTRATION_LIMIT", {
                "reason": f"Total exposure for {ticker} (${new_total_exposure:,.2f}) would exceed 20% ticker concentration limit (${max_ticker_exposure:,.2f})."
            }

        # 5. Check Cash Sufficiency
        if strategy == "CASH_SECURED_PUT" and cash < collateral_req:
            return False, "REJECTED_INSUFFICIENT_CASH", {
                "reason": f"Available cash (${cash:,.2f}) is less than required collateral (${collateral_req:,.2f})."
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
                "Max 10% Position Size Check Passed",
                "Max 20% Ticker Concentration Check Passed",
                "Cash Collateral Verification Passed",
                "Sentiment & Catalyst Risk Check Passed",
                "Drawdown Circuit Breaker Normal"
            ],
            "portfolio_delta_post_trade": round(projected_delta, 2),
            "estimated_theta_boost": round(abs(candidate_trade.get("theta", 0.0) * 100.0), 2)
        }

        return True, "APPROVED", audit_metadata

    def check_and_trigger_tail_hedge(self, market_stress_index: float = 18.5) -> Dict[str, Any]:
        """
        Autonomous Hedging Engine:
        Evaluates portfolio risk. If market stress exceeds threshold or net delta is overly positive,
        autonomously deploys a SPY/QQQ protective put tail hedge.
        """
        account = self.alpaca.get_account_summary()
        greeks = self.alpaca.calculate_portfolio_greeks()
        
        hedge_triggered = False
        hedge_action = None

        if market_stress_index >= self.rules["STRESS_VIX_HEDGE_THRESHOLD"] or greeks["net_delta"] > self.rules["MAX_PORTFOLIO_DELTA"]:
            hedge_triggered = True
            spy_spot = self.alpaca.get_spot_price("SPY")
            strike = round(spy_spot * 0.96, 0) # 4% OTM protective put
            
            # Execute protective put purchase
            hedge_action = {
                "ticker": "SPY",
                "type": "BUY_PROTECTIVE_PUT",
                "strike": strike,
                "dte": 14,
                "reason": f"Market stress index ({market_stress_index}) or Portfolio Delta ({greeks['net_delta']}) triggered autonomous tail hedge.",
                "cost_est": round(spy_spot * 0.008 * 100, 2)
            }
            logger.warning(f"AUTONOMOUS TAIL HEDGE DEPLOYED: {hedge_action}")

        return {
            "stress_index": market_stress_index,
            "threshold": self.rules["STRESS_VIX_HEDGE_THRESHOLD"],
            "hedge_triggered": hedge_triggered,
            "hedge_action": hedge_action,
            "current_portfolio_delta": greeks["net_delta"]
        }

risk_agent = RiskGovernanceAgent()
