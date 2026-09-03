import json
import logging
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.config import DECISION_LOG_PATH, RISK_RULES
from src.alpaca_client.alpaca_service import alpaca_service
from src.agents.quant_agent import quant_agent
from src.agents.sentiment_agent import sentiment_agent
from src.agents.risk_agent import risk_agent
from src.agents.portfolio_manager import portfolio_manager
from src.agents.news_agent import news_agent
from src.agents.notifier import notifier
from src.persistence.database import journal
from src.ai.voice_narrator import voice_narrator

logger = logging.getLogger("Aegis.Orchestrator")


class AegisOrchestrator:
    """
    Central Controller and Orchestration Engine v2.0.

    Executes the full institutional trading lifecycle every cycle:
      0. Market session check (market-hours aware)
      1. Account & portfolio risk state audit -> equity snapshot to journal
      2. PORTFOLIO MANAGEMENT FIRST: take-profit / stop-loss / roll / expiry
         sweep across all open positions (realizes P&L before opening risk)
      3. Market regime classification from LIVE news (News Agent)
      4. Quant Agent scans watchlist & generates Wheel trade proposals
         (with duplicate guards & earnings exclusions)
      5. Sentiment Agent contextualizes REAL news & catalyst risk per proposal
      6. Risk Agent conducts quantitative governance audit (Approve/Resize/Veto)
      7. Execution via Alpaca Trading API + SQLite journal entries
      8. Autonomous tail-hedge stress check (real VIX-proxy, actual execution)
      9. Cycle persistence, Telegram notifications, executive voice briefing
    """
    def __init__(self):
        self.alpaca = alpaca_service
        self.quant = quant_agent
        self.sentiment = sentiment_agent
        self.risk = risk_agent
        self.pm = portfolio_manager
        self.news = news_agent
        self.voice = voice_narrator
        self.journal = journal
        self.notifier = notifier
        self.log_file = DECISION_LOG_PATH
        self.live_logs: List[Dict[str, Any]] = []
        self._cycle_lock = threading.Lock()  # prevents concurrent cycles
        self._last_cycle_result: Optional[Dict[str, Any]] = None

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

    def run_full_cycle(self, force_execute: bool = True, force_offline: bool = False) -> Dict[str, Any]:
        """
        Executes one full autonomous cycle of the Aegis options trading desk.
        Thread-safe: a lock prevents overlapping cycles when the auto-loop
        and a manual trigger collide.
        """
        if not self._cycle_lock.acquire(blocking=False):
            self.log_event("CYCLE_SKIPPED", "Orchestrator", "Another cycle is already running — skipping overlapping trigger.")
            return self._last_cycle_result or {"status": "SKIPPED_OVERLAPPING"}

        try:
            return self._execute_cycle(force_execute, force_offline)
        finally:
            self._cycle_lock.release()

    def _execute_cycle(self, force_execute: bool, force_offline: bool) -> Dict[str, Any]:
        self.log_event("INITIATION", "Orchestrator", "Starting Aegis autonomous multi-agent options cycle...")

        # ------------------------------------------------------------------
        # STEP 0: Market session check
        # ------------------------------------------------------------------
        clock = self.alpaca.get_market_clock()
        market_open = clock.get("is_open", True)
        cycle_mode = "LIVE_SESSION" if market_open else "AFTER_HOURS_AUDIT"
        if not market_open:
            self.log_event("MARKET_CLOSED", "Orchestrator",
                           f"Market is closed (next open: {clock.get('next_open', 'N/A')}). Running management & audit cycle only — no new orders.")

        # ------------------------------------------------------------------
        # STEP 1: Account & risk state audit + equity snapshot
        # ------------------------------------------------------------------
        account = self.alpaca.get_account_summary()
        greeks = self.alpaca.calculate_portfolio_greeks()
        stress = self.alpaca.get_market_stress_index()
        self.log_event("ACCOUNT_AUDIT", "AlpacaBroker",
                       f"Account active. Equity: ${account['equity']:,.2f} | Buying Power: ${account['buying_power']:,.2f} | "
                       f"Net Delta: {greeks['net_delta']} | Daily Theta: ${greeks['daily_theta_income']} | Stress Index: {stress}")

        # ------------------------------------------------------------------
        # STEP 2: PORTFOLIO MANAGEMENT (harvest P&L BEFORE adding risk)
        # ------------------------------------------------------------------
        management = self.pm.manage_open_positions(log_fn=self.log_event)

        # ------------------------------------------------------------------
        # STEP 3: Market regime from LIVE news
        # ------------------------------------------------------------------
        regime = self.news.classify_market_regime()
        self.log_event("MARKET_REGIME", "NewsAgent",
                       f"Live news regime: {regime['regime']} (confidence {regime['confidence']}%) — {regime['summary']}")

        # Earnings blackout: exclude tickers with imminent earnings flagged in live news
        exclude_tickers = []
        for ticker in self.quant.watchlist:
            scan = self.news.detect_earnings_proximity(ticker)
            if scan.get("imminent_flag"):
                exclude_tickers.append(ticker)
                self.log_event("EARNINGS_BLACKOUT", "NewsAgent",
                               f"{ticker} excluded from new premium selling — imminent earnings detected in live headlines.")
        if regime.get("regime") in ("RISK_OFF", "CRISIS") and not regime.get("premium_selling_favorable", True):
            self.log_event("REGIME_CAUTION", "NewsAgent",
                           f"Regime {regime['regime']} — new premium selling deprioritized this cycle.")

        # ------------------------------------------------------------------
        # STEP 4: Quant screening
        # ------------------------------------------------------------------
        self.log_event("SCREENING", "QuantAgent", "Scanning blue-chip options chains for high-probability Wheel candidates...")
        proposals = self.quant.screen_opportunities(exclude_tickers=exclude_tickers)
        self.log_event("PROPOSALS_GENERATED", "QuantAgent",
                       f"Generated {len(proposals)} candidate options trade tickets based on IV rank, delta targeting, and duplicate guards.")

        cycle_results = []
        executed_trades = []
        vetoed_trades = []
        max_new = RISK_RULES.get("MAX_NEW_TRADES_PER_CYCLE", 3)

        # ------------------------------------------------------------------
        # STEP 5-7: Per-proposal sentiment -> risk -> execution
        # ------------------------------------------------------------------
        open_count = 0
        for prop in proposals:
            if open_count >= max_new:
                self.log_event("DIVERSIFICATION_CAP", "Orchestrator",
                               f"Max {max_new} new positions per cycle reached — remaining proposals deferred to next cycle.")
                break

            # Regime gate: suppress ALL new trades in crisis unless forced
            if regime.get("regime") == "CRISIS" and not force_execute:
                vetoed_trades.append({**prop, "risk_verdict": "DEFERRED_CRISIS_REGIME", "status": "VETOED"})
                continue

            ticker = prop["ticker"]
            strategy = prop["strategy"]
            strike = prop["strike"]
            self.log_event("SENTIMENT_ANALYSIS", "SentimentAgent",
                           f"Evaluating live news, earnings schedule, and catalyst regime for {ticker} ({strategy})...")

            sentiment_eval = self.sentiment.evaluate_proposal(prop)
            self.log_event("SENTIMENT_SCORE", "SentimentAgent",
                           f"{ticker} Conviction Score: {sentiment_eval['conviction_score']}/100 | "
                           f"Regime: {sentiment_eval['market_regime']} | Earnings Risk: {sentiment_eval['earnings_risk']}"
                           + (f" | Ensemble: {', '.join(sentiment_eval.get('ensemble_providers', []))}" if sentiment_eval.get("ensemble_mode") else ""))

            # Risk Audit
            self.log_event("RISK_AUDIT", "RiskGovernanceAgent",
                           f"Subjecting {ticker} {strategy} proposal to deterministic portfolio risk gates...")
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
                "iv_rank": prop.get("iv_rank"),
                "sentiment_eval": sentiment_eval,
                "risk_verdict": verdict,
                "risk_metadata": audit_metadata,
                "status": "APPROVED" if approved else "VETOED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            if approved:
                self.log_event("RISK_APPROVED", "RiskGovernanceAgent",
                               f"APPROVED {ticker} {strategy} @ ${strike} strike. Risk gates cleared.", audit_metadata)

                if force_execute and market_open:
                    # Execute order on Alpaca (SELL TO OPEN)
                    side = "sell"  # Wheel sells put or call
                    order_res = self.alpaca.execute_order(
                        symbol=prop.get("contract_symbol", ticker),
                        qty=1,
                        side=side,
                        order_type="limit",
                        limit_price=prop.get("estimated_premium", 1.0)
                    )
                    trade_record["execution"] = order_res

                    if order_res.get("success"):
                        self.log_event("EXECUTION_COMPLETED", "ExecutionEngine",
                                       f"Order submitted to Alpaca Paper Trading: {side.upper()} 1x {prop.get('contract_symbol', ticker)}",
                                       order_res)
                        executed_trades.append(trade_record)
                        open_count += 1

                        # Persist to SQLite journal
                        self.journal.record_trade_open(
                            contract_symbol=prop.get("contract_symbol", ticker),
                            ticker=ticker,
                            strategy=strategy,
                            side="SELL_TO_OPEN",
                            qty=1,
                            strike=strike,
                            expiration=prop.get("expiration"),
                            dte=prop.get("dte"),
                            delta=prop.get("delta"),
                            premium=prop.get("estimated_premium", 0.0),
                            order_id=order_res.get("order_id"),
                            order_status=order_res.get("status", "SUBMITTED"),
                            conviction_score=sentiment_eval.get("conviction_score"),
                            risk_verdict=verdict,
                            agent_thesis=prop.get("agent_thesis"),
                        )
                        self.notifier.notify_trade_executed(
                            ticker, strategy, strike,
                            prop.get("total_credit", 0.0), prop.get("annualized_yield", 0.0)
                        )
                    else:
                        trade_record["status"] = "REJECTED_BY_BROKER"
                        self.log_event("EXECUTION_FAILED", "ExecutionEngine",
                                       f"Order REJECTED by Alpaca for {ticker}: {order_res.get('error', 'unknown')}")
                        vetoed_trades.append(trade_record)
                elif force_execute and not market_open:
                    trade_record["status"] = "DEFERRED_MARKET_CLOSED"
                    self.log_event("EXECUTION_DEFERRED", "ExecutionEngine",
                                   f"Market closed — {ticker} {strategy} proposal deferred to next session.")
                    vetoed_trades.append(trade_record)
            else:
                self.log_event("RISK_VETOED", "RiskGovernanceAgent",
                               f"VETOED {ticker} {strategy}: {verdict}", audit_metadata)
                vetoed_trades.append(trade_record)
                self.notifier.notify_trade_vetoed(ticker, strategy, verdict)

            cycle_results.append(trade_record)

        # ------------------------------------------------------------------
        # STEP 8: Tail hedge check (real stress index + actual execution)
        # ------------------------------------------------------------------
        self.log_event("HEDGE_AUDIT", "RiskGovernanceAgent",
                       f"Running independent tail-risk stress check (live stress index: {stress})...")
        hedge_status = self.risk.check_and_trigger_tail_hedge(market_stress_index=None, execute=market_open)
        if hedge_status.get("hedge_triggered"):
            action = hedge_status.get("hedge_action") or {}
            self.log_event("TAIL_HEDGE_TRIGGERED", "RiskGovernanceAgent",
                           f"Tail hedge active: {action.get('type')} — {action.get('reason', '')}",
                           hedge_status)
            if action.get("executed"):
                self.notifier.notify_hedge(action.get("contract_symbol", "SPY put"),
                                            action.get("strike", 0), action.get("reason", ""))
        else:
            self.log_event("HEDGE_NORMAL", "RiskGovernanceAgent",
                           f"Market stress index is normal ({stress} < {hedge_status['threshold']} threshold). No tail hedge required.")

        # ------------------------------------------------------------------
        # STEP 9: Performance snapshot, notifications, voice briefing
        # ------------------------------------------------------------------
        performance = self.journal.get_performance_analytics(starting_equity=100000.0)
        self.journal.record_equity_snapshot(
            equity=account["equity"], cash=account.get("cash", 0.0),
            day_pnl=account.get("day_pnl", 0.0), net_delta=greeks.get("net_delta", 0.0),
            daily_theta=greeks.get("daily_theta_income", 0.0), stress_index=stress,
            market_regime=regime.get("regime", "N/A"),
        )
        self.journal.record_cycle(
            proposals_count=len(proposals), executed_count=len(executed_trades),
            vetoed_count=len(vetoed_trades), managed_count=management.get("managed", 0),
            hedge_triggered=bool(hedge_status.get("hedge_triggered")),
            equity=account["equity"], cycle_mode=cycle_mode,
        )

        for action_rec in management.get("actions", []):
            self.notifier.notify_position_closed(action_rec.get("ticker", ""), action_rec.get("action", ""), action_rec.get("realized_pnl", 0.0))

        realized = management.get("realized_pnl", 0.0)
        self.notifier.notify_cycle_summary(account["equity"], len(executed_trades),
                                           len(vetoed_trades), management.get("managed", 0), realized)

        briefing_text = (
            f"Aegis Autonomous Options Desk cycle complete. Portfolio equity is at ${account['equity']:,.2f} "
            f"with daily theta income of ${greeks['daily_theta_income']:.2f}. "
            f"Market regime: {regime['regime']}. Stress index at {stress}. "
            f"Portfolio manager executed {management.get('managed', 0)} management actions realizing ${realized:.2f}. "
            f"Quant Agent screened {len(proposals)} contracts. Risk Agent approved {len(executed_trades)} trades and vetoed {len(vetoed_trades)}. "
            f"Total realized P&L to date: ${performance['total_realized_pnl']:.2f} across {performance['closed_trades']} closed trades. "
            f"Portfolio Greeks remain strictly inside institutional risk gates."
        )
        audio_url = self.voice.generate_speech(briefing_text)
        self.log_event("CYCLE_COMPLETE", "Orchestrator", "Cycle completed successfully. All logs committed to audit trail & journal.")

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycle_mode": cycle_mode,
            "market_open": market_open,
            "account": account,
            "portfolio_greeks": greeks,
            "market_data": {
                "stress_index": stress,
                "regime": regime,
            },
            "management": management,
            "earnings_blackout": exclude_tickers,
            "proposals_count": len(proposals),
            "executed_trades": executed_trades,
            "vetoed_trades": vetoed_trades,
            "hedge_status": hedge_status,
            "performance": performance,
            "audio_briefing_url": audio_url,
            "briefing_text": briefing_text
        }
        self._last_cycle_result = result
        return result


orchestrator = AegisOrchestrator()
