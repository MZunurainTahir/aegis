import unittest
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.alpaca_client.alpaca_service import alpaca_service, BlackScholesCalculator
from src.agents.quant_agent import quant_agent
from src.agents.sentiment_agent import sentiment_agent
from src.agents.risk_agent import risk_agent
from src.agents.orchestrator import orchestrator

class TestAegisEngine(unittest.TestCase):

    def test_01_black_scholes_calculator(self):
        """Verify Black-Scholes Greeks calculation accuracy."""
        calc = BlackScholesCalculator()
        greeks = calc.calculate_greeks(spot=100.0, strike=95.0, dte_days=30, iv=0.25, option_type="put")
        self.assertIn("delta", greeks)
        self.assertIn("theta", greeks)
        self.assertIn("vega", greeks)
        self.assertLess(greeks["delta"], 0.0) # Put delta is negative
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
            "collateral_required": 75000.0, # Exceeds 35% limit on $100k account
            "delta": -0.25,
            "theta": -0.05
        }
        sentiment_eval = {"conviction_score": 80, "veto_recommended": False}
        approved, verdict, meta = risk_agent.audit_trade_proposal(huge_trade, sentiment_eval)
        self.assertFalse(approved)
        self.assertEqual(verdict, "REJECTED_POSITION_SIZE_EXCEEDED")

    def test_06_autonomous_tail_hedge(self):
        """Verify Risk Agent triggers protective put hedge upon market stress."""
        # Test normal stress
        normal = risk_agent.check_and_trigger_tail_hedge(market_stress_index=15.0)
        self.assertFalse(normal["hedge_triggered"])

        # Test high stress (> 25.0 threshold)
        high_stress = risk_agent.check_and_trigger_tail_hedge(market_stress_index=32.0)
        self.assertTrue(high_stress["hedge_triggered"])
        self.assertEqual(high_stress["hedge_action"]["type"], "BUY_PROTECTIVE_PUT")

if __name__ == "__main__":
    unittest.main()
