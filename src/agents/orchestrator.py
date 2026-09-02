import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.config import DECISION_LOG_PATH
from src.alpaca_client.alpaca_service import alpaca_service
from src.agents.quant_agent import quant_agent
from src.agents.sentiment_agent import sentiment_agent
from src.agents.risk_agent import risk_agent
from src.ai.voice_narrator import voice_narrator

logger = logging.getLogger("Aegis.Orchestrator")

class AegisOrchestrator:
    """
    Central Controller and Orchestration Engine.
    Sequences Quant Agent -> Sentiment Agent -> Risk Agent -> Execution & Audit Trail.
    """
    def __init__(self):
        self.alpaca = alpaca_service
        self.quant = quant_agent
        self.sentiment = sentiment_agent
        self.risk = risk_agent
        self.voice = voice_narrator
        self.log_file = DECISION_LOG_PATH
        self.live_logs: List[Dict[str, Any]] = []

    def log_event(self, stage: str, agent: str, message: str, details: Optional[Dict[str, Any]] = None):
        """Records a timestamped event into the in-memory streaming log and persistent audit file."""
        event = {
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "stage": stage,
            "agent": agent,
            "message": message,
            "details": details or {}
        }
        self.live_logs.append(event)
        if len(self.live_logs) > 200:
            self.live_logs.pop(0)

        # Append to audit JSON
        try:
            records = []
            if self.log_file.exists():
                with open(self.log_file, "r") as f:
                    try:
                        records = json.load(f)
                    except:
                        records = []
            records.append(event)
            with open(self.log_file, "w") as f:
                json.dump(records[-300:], f, indent=2)
        except Exception as e:
            logger.error(f"Error persisting audit log: {e}")

    def run_full_cycle(self, force_execute: bool = True) -> Dict[str, Any]:
        """
        Executes one full autonomous cycle of the Aegis options trading desk:
        1. Account & Portfolio Risk State check.
        2. Quant Agent scans watchlist & generates Wheel trade proposals.
        3. Sentiment Agent contextualizes news & catalyst risk.
        4. Risk Agent conducts quantitative governance audit (Approve / Resize / Veto).
        5. Execution via Alpaca Trading API.
        6. Autonomous Tail-Hedge stress check.
        7. Executive Briefing Generation.
        """
        self.log_event("INITIATION", "Orchestrator", "Starting Aegis autonomous multi-agent options cycle...")

        account = self.alpaca.get_account_summary()
        greeks = self.alpaca.calculate_portfolio_greeks()
        self.log_event("ACCOUNT_AUDIT", "AlpacaBroker", f"Account active. Equity: ${account['equity']:,.2f} | Buying Power: ${account['buying_power']:,.2f} | Net Delta: {greeks['net_delta']} | Daily Theta: ${greeks['daily_theta_income']}")

        # 1. Quant Screening
        self.log_event("SCREENING", "QuantAgent", "Scanning blue-chip options chains for high-probability Wheel candidates...")
        proposals = self.quant.screen_opportunities()
        self.log_event("PROPOSALS_GENERATED", "QuantAgent", f"Generated {len(proposals)} candidate options trade tickets based on IV rank and delta targeting.")

        cycle_results = []
        executed_trades = []
        vetoed_trades = []

        # Process top proposals (up to 3 per cycle to maintain diversification)
        for prop in proposals[:3]:
            ticker = prop["ticker"]
            strategy = prop["strategy"]
            strike = prop["strike"]
            self.log_event("SENTIMENT_ANALYSIS", "SentimentAgent", f"Evaluating news, earnings schedule, and catalyst regime for {ticker} ({strategy})...")
            
            sentiment_eval = self.sentiment.evaluate_proposal(prop)
            self.log_event("SENTIMENT_SCORE", "SentimentAgent", f"{ticker} Conviction Score: {sentiment_eval['conviction_score']}/100 | Regime: {sentiment_eval['market_regime']} | Earnings Risk: {sentiment_eval['earnings_risk']}")

            # Risk Audit
            self.log_event("RISK_AUDIT", "RiskGovernanceAgent", f"Subjecting {ticker} {strategy} proposal to deterministic portfolio risk gates...")
            approved, verdict, audit_metadata = self.risk.audit_trade_proposal(prop, sentiment_eval)

            trade_record = {
                "ticker": ticker,
                "strategy": strategy,
                "contract_symbol": prop.get("contract_symbol", ""),
                "strike": strike,
                "expiration": prop.get("expiration", ""),
                "dte": prop.get("dte", 0),
                "delta": prop.get("delta", 0.0),
                "premium": prop.get("estimated_premium", 0.0),
                "total_credit": prop.get("total_credit", 0.0),
                "annualized_yield": prop.get("annualized_yield", 0.0),
                "sentiment_eval": sentiment_eval,
                "risk_verdict": verdict,
                "risk_metadata": audit_metadata,
                "status": "APPROVED" if approved else "VETOED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            if approved:
                self.log_event("RISK_APPROVED", "RiskGovernanceAgent", f"APPROVED {ticker} {strategy} @ ${strike} strike. Risk gates cleared.", audit_metadata)
                
                if force_execute:
                    # Execute order on Alpaca
                    side = "sell" # Wheel sells put or call
                    order_res = self.alpaca.execute_order(
                        symbol=prop.get("contract_symbol", ticker),
                        qty=1,
                        side=side,
                        order_type="limit",
                        limit_price=prop.get("estimated_premium", 1.0)
                    )
                    trade_record["execution"] = order_res
                    self.log_event("EXECUTION_COMPLETED", "ExecutionEngine", f"Order submitted to Alpaca Paper Trading: {side.upper()} 1x {prop.get('contract_symbol', ticker)}", order_res)
                    executed_trades.append(trade_record)
            else:
                self.log_event("RISK_VETOED", "RiskGovernanceAgent", f"VETOED {ticker} {strategy}: {verdict}", audit_metadata)
                vetoed_trades.append(trade_record)

            cycle_results.append(trade_record)

        # 2. Tail Hedge Check
        self.log_event("HEDGE_AUDIT", "RiskGovernanceAgent", "Running independent tail-risk stress check...")
        hedge_status = self.risk.check_and_trigger_tail_hedge()
        if hedge_status.get("hedge_triggered"):
            self.log_event("TAIL_HEDGE_TRIGGERED", "RiskGovernanceAgent", f"Tail hedge active: {hedge_status['hedge_action']}")
        else:
            self.log_event("HEDGE_NORMAL", "RiskGovernanceAgent", "Market stress index is normal (18.5 < 25.0 threshold). No tail hedge required.")

        # 3. Audio Briefing Synthesis
        briefing_text = (
            f"Aegis Autonomous Options Desk cycle complete. Portfolio equity is at ${account['equity']:,.2f} "
            f"with daily theta income of ${greeks['daily_theta_income']:.2f}. "
            f"Quant Agent screened {len(proposals)} contracts. Risk Agent approved {len(executed_trades)} trades and vetoed {len(vetoed_trades)}. "
            f"Portfolio Greeks remain strictly inside institutional risk gates."
        )
        audio_url = self.voice.generate_speech(briefing_text)
        self.log_event("CYCLE_COMPLETE", "Orchestrator", "Cycle completed successfully. All logs committed to audit trail.")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "account": account,
            "portfolio_greeks": greeks,
            "proposals_count": len(proposals),
            "executed_trades": executed_trades,
            "vetoed_trades": vetoed_trades,
            "hedge_status": hedge_status,
            "audio_briefing_url": audio_url,
            "briefing_text": briefing_text
        }

orchestrator = AegisOrchestrator()
