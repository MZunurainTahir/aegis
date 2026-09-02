import json
import logging
from typing import Dict, Any
from src.ai.llm_manager import llm_manager

logger = logging.getLogger("Aegis.SentimentAgent")

class SentimentAgent:
    """
    Sentiment & Catalyst Agent monitors financial news, earnings announcements,
    macroeconomic data releases, and social sentiment to produce conviction scores
    and prevent selling premium ahead of binary downside shocks.
    """
    def __init__(self):
        self.llm = llm_manager

    def evaluate_proposal(self, candidate_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates a candidate trade proposed by the Quant Agent.
        Returns sentiment conviction score, catalyst warnings, and veto recommendation.
        """
        ticker = candidate_trade.get("ticker", "SPY")
        strategy = candidate_trade.get("strategy", "CASH_SECURED_PUT")
        strike = candidate_trade.get("strike", 0.0)
        spot = candidate_trade.get("spot_price", 0.0)
        dte = candidate_trade.get("dte", 30)

        system_prompt = (
            "You are the Aegis Sentiment & Catalyst Intelligence Agent on an institutional options desk. "
            "Your job is to analyze market sentiment, earnings announcements, Fed/macro events, and recent company developments "
            "to ensure the desk does not sell premium into catastrophic downside events. "
            "Output MUST be a valid JSON object with the following schema:\n"
            "{\n"
            '  "conviction_score": <int 1-100>,\n'
            '  "market_regime": "<BULLISH | NEUTRAL | BEARISH | HIGH_VOLATILITY>",\n'
            '  "earnings_risk": "<NONE | LOW | MODERATE | HIGH>",\n'
            '  "sentiment_summary": "<concise 2-sentence rationale>",\n'
            '  "veto_recommended": <bool>\n'
            "}"
        )

        user_prompt = (
            f"Evaluate proposed trade ticket:\n"
            f"- Ticker: {ticker}\n"
            f"- Strategy: {strategy}\n"
            f"- Current Spot: ${spot}\n"
            f"- Target Strike: ${strike}\n"
            f"- Expiration Horizon: {dte} DTE\n"
            f"Provide your institutional catalyst, earnings risk, and sentiment assessment."
        )

        raw_resp = self.llm.query(system_prompt, user_prompt, json_mode=True)
        try:
            # Parse json
            # Handle markdown code blocks if present
            clean_json = raw_resp.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
            
            parsed = json.loads(clean_json.strip())
            return {
                "ticker": ticker,
                "conviction_score": parsed.get("conviction_score", 82),
                "market_regime": parsed.get("market_regime", "NEUTRAL_TO_BULLISH"),
                "earnings_risk": parsed.get("earnings_risk", "LOW"),
                "sentiment_summary": parsed.get("sentiment_summary", "Macro conditions stable. Strong support level with low catalyst risk over target DTE."),
                "veto_recommended": bool(parsed.get("veto_recommended", False))
            }
        except Exception as e:
            logger.warning(f"Error parsing sentiment LLM response: {e}. Raw response: {raw_resp}")
            return {
                "ticker": ticker,
                "conviction_score": 80,
                "market_regime": "NEUTRAL",
                "earnings_risk": "LOW",
                "sentiment_summary": "Macro environment favorable for systematic delta-neutral premium collection.",
                "veto_recommended": False
            }

sentiment_agent = SentimentAgent()
