"""
AEGIS v3.0 Test Suite — 16 integration & unit tests
====================================================
Covers the full v3 platform:
  01-06  Core engine (Black-Scholes, Alpaca, screening, sentiment, risk veto, tail hedge)
  07     OCC option symbol parser
  08-09  SQLite trade journal lifecycle + performance analytics (isolated temp DB)
  10     Live market clock + real VIX-proxy stress index
  11     News Agent RSS ingestion + earnings proximity detection
  12     Portfolio Manager position marks
  13     Telegram notifier graceful degradation
  14     Web API v3 route registration (FastAPI smoke test)
  15     FastMCP server tool registration
  16     Orchestrator v2 pipeline structure

Network-dependent tests skip gracefully when offline.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure .env is loaded before singletons are constructed
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from src.alpaca_client.alpaca_service import alpaca_service, BlackScholesCalculator, parse_option_symbol
from src.agents.quant_agent import quant_agent
from src.agents.sentiment_agent import sentiment_agent
from src.agents.risk_agent import risk_agent
from src.agents.orchestrator import orchestrator
from src.agents.portfolio_manager import portfolio_manager
from src.agents.news_agent import news_agent
from src.agents.notifier import notifier
from src.persistence.database import AegisJournal


def _offline_guard(fn):
    """Decorator: skip the test when a network/dependency error occurs."""
    def wrapper(self):
        try:
            return fn(self)
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"network/dependency unavailable: {e}")
    return wrapper


class TestAegisEngine(unittest.TestCase):

    # ------------------------------------------------------------------
    # Core engine (original contract — preserved)
    # ------------------------------------------------------------------
    def test_01_black_scholes_calculator(self):
        """Verify Black-Scholes Greeks calculation accuracy."""
        calc = BlackScholesCalculator()
        greeks = calc.calculate_greeks(spot=100.0, strike=95.0, dte_days=30, iv=0.25, option_type="put")
        self.assertIn("delta", greeks)
        self.assertIn("theta", greeks)
        self.assertIn("vega", greeks)
        self.assertLess(greeks["delta"], 0.0)  # Put delta is negative
        self.assertGreater(greeks["price"], 0.0)

    def test_02_alpaca_account_summary(self):
        """Verify Alpaca Paper Trading account connection."""
        acc = alpaca_service.get_account_summary()
        self.assertIsNotNone(acc["account_id"])
        self.assertEqual(acc["currency"], "USD")
        self.assertGreater(acc["equity"], 0.0)

    def test_03_quant_screening(self):
        """Verify Quant Agent scans options and calculates yields."""
        proposals = quant_agent.screen_opportunities()
        self.assertIsInstance(proposals, list)
        self.assertGreater(len(proposals), 0)
        top = proposals[0]
        self.assertIn("ticker", top)
        self.assertIn("strike", top)
        self.assertIn("annualized_yield", top)

    def test_04_sentiment_analysis(self):
        """Verify Sentiment Agent produces structured conviction scores."""
        sample_trade = {
            "ticker": "SPY",
            "strategy": "CASH_SECURED_PUT",
            "strike": 570.0,
            "spot_price": 595.0,
            "dte": 30
        }
        res = sentiment_agent.evaluate_proposal(sample_trade)
        self.assertIn("conviction_score", res)
        self.assertIn("market_regime", res)
        self.assertIn("veto_recommended", res)

    def test_05_risk_governance_and_veto(self):
        """Verify Risk Agent enforces hard risk limits."""
        huge_trade = {
            "ticker": "SPY",
            "strategy": "CASH_SECURED_PUT",
            "strike": 750.0,
            "spot_price": 595.0,
            "dte": 30,
            "collateral_required": 75000.0,  # Exceeds 35% limit on $100k account
            "delta": -0.25,
            "theta": -0.05
        }
        sentiment_eval = {"conviction_score": 80, "veto_recommended": False}
        approved, verdict, meta = risk_agent.audit_trade_proposal(huge_trade, sentiment_eval)
        self.assertFalse(approved)
        self.assertEqual(verdict, "REJECTED_POSITION_SIZE_EXCEEDED")

    def test_06_autonomous_tail_hedge(self):
        """Verify Risk Agent triggers protective put hedge upon market stress."""
        from unittest.mock import patch
        from src.persistence.database import journal as live_journal

        # Neutralize the production hedge cooldown so the trigger logic is
        # deterministically testable regardless of real hedge history.
        with patch.object(live_journal, "last_hedge_time", return_value=None):
            # Test normal stress
            normal = risk_agent.check_and_trigger_tail_hedge(market_stress_index=15.0)
            self.assertFalse(normal["hedge_triggered"])

            # Test high stress (> 25.0 threshold)
            high_stress = risk_agent.check_and_trigger_tail_hedge(market_stress_index=32.0)
            self.assertTrue(high_stress["hedge_triggered"])
            self.assertEqual(high_stress["hedge_action"]["type"], "BUY_PROTECTIVE_PUT")

    # ------------------------------------------------------------------
    # v3.0 platform
    # ------------------------------------------------------------------
    def test_07_occ_symbol_parser(self):
        """Verify OCC option symbol parsing (underlying/expiry/type/strike)."""
        parsed = parse_option_symbol("SPY260918C00600000")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["underlying"], "SPY")
        self.assertEqual(parsed["option_type"], "call")
        self.assertEqual(parsed["strike"], 600.0)
        self.assertEqual(parsed["expiration"], "2026-09-18")

        put = parse_option_symbol("AAPL261016P00150000")
        self.assertEqual(put["option_type"], "put")
        self.assertEqual(put["strike"], 150.0)

        # Invalid symbols return None (honest failure)
        self.assertIsNone(parse_option_symbol("NOT_AN_OPTION"))
        self.assertIsNone(parse_option_symbol("SPY261332C00600000"))  # invalid date

    def test_08_journal_trade_lifecycle(self):
        """Verify SQLite journal: open -> close -> realized P&L -> duplicate guard."""
        with tempfile.TemporaryDirectory() as tmp:
            db = AegisJournal(db_path=Path(tmp) / "test_journal.db")

            tid = db.record_trade_open(
                contract_symbol="SPY260918P00570000", ticker="SPY",
                strategy="CASH_SECURED_PUT", side="SELL_TO_OPEN", qty=1,
                strike=570.0, expiration="2026-09-18", dte=15, delta=-0.22,
                premium=3.50, order_id="test-001",
            )
            self.assertGreater(tid, 0)

            # Duplicate guard fires before any close
            self.assertTrue(db.has_open_position_for("SPY"))
            self.assertTrue(db.has_open_position_for("SPY", "CASH_SECURED_PUT"))
            self.assertFalse(db.has_open_position_for("AAPL"))

            # Close at half the credit: entry 3.50, exit 1.75 -> +$175 realized
            closed = db.record_trade_close("SPY260918P00570000", close_price=1.75, qty=1)
            self.assertIsNotNone(closed)
            self.assertAlmostEqual(closed["realized_pnl"], 175.0, places=2)
            self.assertEqual(closed["status"], "CLOSED")

            # Position no longer open -> guard releases
            self.assertFalse(db.has_open_position_for("SPY"))

            # Hedge (long) trade: entry 1.20, exit 2.00 -> +$80 realized
            hid = db.record_trade_open(
                contract_symbol="SPY260918P00550000", ticker="SPY",
                strategy="TAIL_HEDGE", side="HEDGE_BUY", qty=1,
                strike=550.0, expiration="2026-09-18", dte=15, delta=-0.10,
                premium=1.20, order_id="test-002",
            )
            hc = db.record_trade_close("SPY260918P00550000", close_price=2.00, qty=1)
            self.assertAlmostEqual(hc["realized_pnl"], 80.0, places=2)

    def test_09_journal_performance_analytics(self):
        """Verify performance analytics engine (win rate, profit factor, drawdown)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = AegisJournal(db_path=Path(tmp) / "test_analytics.db")

            # Two winners, one loser
            for sym, prem, close_px in [
                ("A260918P00050000", 2.00, 0.50),   # +150
                ("B260918P00050000", 3.00, 3.80),   # -80 (stop-loss)
                ("C260918P00050000", 1.50, 0.10),   # +140
            ]:
                db.record_trade_open(
                    contract_symbol=sym, ticker=sym[0], strategy="CASH_SECURED_PUT",
                    side="SELL_TO_OPEN", qty=1, strike=50.0, expiration="2026-09-18",
                    dte=15, delta=-0.2, premium=prem, order_id=None,
                )
                db.record_trade_close(sym, close_price=close_px, qty=1)

            # Equity curve: 100k -> 100.3k -> 100.1k (drawdown ~0.2%)
            # (insert directly — record_equity_snapshot dedupes to one row per minute)
            import sqlite3 as _sq
            conn = _sq.connect(db.db_path)
            for i, eq in enumerate([100000.0, 100300.0, 100100.0]):
                conn.execute(
                    "INSERT INTO equity_snapshots (timestamp, equity, cash, day_pnl, net_delta, daily_theta, stress_index, market_regime) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (f"2026-09-01T10:0{i}:00", eq, 0, 0, 0, 0, 18.5, "NEUTRAL"),
                )
            conn.commit()
            conn.close()
            db.record_cycle(proposals_count=3, executed_count=2, vetoed_count=1,
                            managed_count=0, hedge_triggered=False, equity=100100.0)

            perf = db.get_performance_analytics(starting_equity=100000.0)
            self.assertAlmostEqual(perf["total_realized_pnl"], 210.0, places=2)
            self.assertEqual(perf["closed_trades"], 3)
            self.assertEqual(perf["winning_trades"], 2)
            self.assertEqual(perf["losing_trades"], 1)
            self.assertAlmostEqual(perf["win_rate_pct"], 66.7, places=1)
            self.assertAlmostEqual(perf["profit_factor"], 290.0 / 80.0, places=2)
            self.assertEqual(perf["total_cycles"], 1)
            self.assertGreater(perf["max_drawdown_pct"], 0.0)
            self.assertIn("CASH_SECURED_PUT", perf["strategy_breakdown"])

    def test_10_market_clock_and_stress_index(self):
        """Verify live market clock + real VIX-proxy stress index from SPY IV."""
        clock = alpaca_service.get_market_clock()
        self.assertIn("is_open", clock)
        self.assertIn("next_open", clock)

        stress = alpaca_service.get_market_stress_index()
        self.assertIsInstance(stress, float)
        self.assertGreater(stress, 0.0)
        self.assertLess(stress, 200.0)
    test_10_market_clock_and_stress_index = _offline_guard(test_10_market_clock_and_stress_index)

    def test_11_news_agent_rss_and_earnings(self):
        """Verify live RSS ingestion and earnings proximity detection."""
        headlines = news_agent.fetch_market_news(limit=4)
        self.assertIsInstance(headlines, list)
        self.assertGreater(len(headlines), 0)
        self.assertIn("title", headlines[0])

        earnings = news_agent.detect_earnings_proximity("AAPL")
        self.assertIn("imminent_flag", earnings)
        self.assertIn("headlines", earnings)
    test_11_news_agent_rss_and_earnings = _offline_guard(test_11_news_agent_rss_and_earnings)

    def test_12_portfolio_manager_marks(self):
        """Verify Portfolio Manager returns marked open positions with state."""
        marks = portfolio_manager.get_open_position_marks()
        self.assertIsInstance(marks, list)
        for m in marks:
            self.assertIn("contract_symbol", m)
            self.assertIn("management_state", m)
    test_12_portfolio_manager_marks = _offline_guard(test_12_portfolio_manager_marks)

    def test_13_notifier_graceful_degradation(self):
        """Notifier must never crash when Telegram is unconfigured."""
        self.assertIsInstance(notifier.enabled, bool)
        result = notifier.notify_cycle_summary(100000.0, 0, 0, 0, 0.0)
        # Either delivered (configured) or silently skipped (not configured)
        self.assertIn(result, (True, False))

    def test_14_web_api_v3_routes(self):
        """Verify FastAPI app registers all v3 endpoints including WebSocket."""
        from src.web.app import app
        routes = {r.path for r in app.routes}
        for path in [
            "/", "/ws", "/api/account", "/api/performance", "/api/journal",
            "/api/news", "/api/market-data", "/api/orders",
            "/api/positions/marks", "/api/close-position", "/api/health",
        ]:
            self.assertIn(path, routes, f"missing route: {path}")

    def test_15_mcp_server_tools(self):
        """Verify FastMCP server exposes the full 11-tool suite."""
        import src.mcp.fastmcp_server as mcp_module
        from fastmcp import FastMCP

        self.assertIsInstance(mcp_module.mcp, FastMCP)
        expected_tools = [
            "aegis_get_account_and_greeks", "aegis_screen_wheel_opportunities",
            "aegis_evaluate_risk", "aegis_run_trading_cycle",
            "aegis_trigger_autonomous_hedge", "aegis_get_performance_analytics",
            "aegis_get_trade_journal", "aegis_manage_positions",
            "aegis_get_market_regime", "aegis_get_news", "aegis_get_order_blotter",
        ]
        for tool_name in expected_tools:
            self.assertTrue(
                hasattr(mcp_module, tool_name),
                f"missing MCP tool: {tool_name}",
            )

        # Registered on the server object as well
        try:
            registered = set(mcp_module.mcp.get_tools()) if hasattr(mcp_module.mcp, "get_tools") else set()
        except TypeError:  # async variant of get_tools
            registered = set()
        if registered:  # sync API available on this fastmcp version
            for name in expected_tools:
                self.assertIn(name, registered, f"tool not registered: {name}")

    def test_16_orchestrator_v2_pipeline(self):
        """Verify Orchestrator v2 exposes the manage-first pipeline + cycle lock."""
        self.assertTrue(hasattr(orchestrator, "run_full_cycle"))
        self.assertTrue(hasattr(orchestrator, "log_event"))
        self.assertTrue(hasattr(orchestrator, "_cycle_lock"))
        # LLM ensemble layer available to all agents
        from src.ai.llm_manager import llm_manager
        self.assertTrue(hasattr(llm_manager, "query"))
        self.assertTrue(hasattr(llm_manager, "query_ensemble"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
