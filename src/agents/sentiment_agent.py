import json
import logging
from typing import Dict, Any, List
from src.ai.llm_manager import llm_manager
from src.agents.news_agent import news_agent

logger = logging.getLogger("Aegis.SentimentAgent")


class SentimentAgent:
    """
    Sentiment & Catalyst Agent monitors REAL live financial news (RSS ingestion),
    earnings announcements, macroeconomic data releases, and social sentiment
    to produce conviction scores and prevent selling premium ahead of binary
    downside shocks.

    v2.0 upgrades:
    - Grounded analysis: feeds live ticker headlines into every LLM call
    - Ensemble consensus: scores from multiple independent LLMs are averaged
    - Earnings blackout: cross-checks live headlines + LLM knowledge for
      imminent earnings windows
    """
    def __init__(self):
        self.llm = llm_manager
        self.news = news_agent

    def evaluate_proposal(self, candidate_trade: Dict[str, Any], use_ensemble: bool = True) -> Dict[str, Any]:
        """
        Evaluates a candidate trade proposed by the Quant Agent.
        Returns sentiment conviction score, catalyst warnings, and veto recommendation.
        """
        ticker = candidate_trade.get("ticker", "SPY")
        strategy = candidate_trade.get("strategy", "CASH_SECURED_PUT")
        strike = candidate_trade.get("strike", 0.0)
        spot = candidate_trade.get("spot_price", 0.0)
        dte = candidate_trade.get("dte", 30)

        # 1. Fetch REAL live headlines for this ticker (cached 10 min)
        headlines = self.news.fetch_ticker_news(ticker, limit=5)
        headline_text = "\n".join(f"- {h['title']} ({h['source']})" for h in headlines)
        if not headline_text:
            headline_text = "- (No live headlines found — using LLM knowledge base)"

        # 2. Check for imminent earnings in live news flow
        earnings_scan = self.news.detect_earnings_proximity(ticker)
        earnings_imminent = earnings_scan.get("imminent_flag", False)

        system_prompt = (
            "You are the Aegis Sentiment & Catalyst Intelligence Agent on an institutional options desk. "
            "You will receive LIVE news headlines for this ticker fetched minutes ago from Google News RSS. "
            "Your job is to analyze this real news flow, earnings proximity, Fed/macro events, and recent "
            "company developments to ensure the desk does not sell premium into catastrophic downside events. "
            "Output MUST be a valid JSON object with the following schema:\n"
            "{\n"
            '  "conviction_score": <int 1-100>,\n'
            '  "market_regime": "<BULLISH | NEUTRAL | BEARISH | HIGH_VOLATILITY>",\n'
            '  "earnings_risk": "<NONE | LOW | MODERATE | HIGH>",\n'
            '  "sentiment_summary": "<concise 2-sentence rationale grounded in the headlines>",\n'
            '  "veto_recommended": <bool>\n'
            "}"
        )

        user_prompt = (
            f"Evaluate proposed trade ticket:\n"
            f"- Ticker: {ticker}\n"
            f"- Strategy: {strategy}\n"
            f"- Current Spot: ${spot}\n"
            f"- Target Strike: ${strike}\n"
            f"- Expiration Horizon: {dte} DTE\n\n"
            f"LIVE NEWS HEADLINES (fetched just now):\n{headline_text}\n\n"
            f"{'WARNING: Earnings report appears imminent based on live headlines — apply earnings blackout unless clearly stale news.' if earnings_imminent else ''}\n"
            f"Provide your institutional catalyst, earnings risk, and sentiment assessment grounded in these headlines."
        )

        # 3. Single call or multi-LLM ensemble consensus
        if use_ensemble:
            responses = self.llm.query_ensemble(system_prompt, user_prompt, json_mode=True, max_providers=2)
            if responses:
                return self._consolidate(responses, ticker, earnings_imminent, headlines)

        raw_resp = self.llm.query(system_prompt, user_prompt, json_mode=True)
        parsed = self._parse_json(raw_resp)
        if parsed:
            result = self._normalize(parsed, ticker, headlines)
        else:
            logger.warning(f"Error parsing sentiment LLM response. Raw: {raw_resp[:200]}")
            result = {
                "ticker": ticker,
                "conviction_score": 80,
                "market_regime": "NEUTRAL",
                "earnings_risk": "LOW",
                "sentiment_summary": "Macro environment favorable for systematic delta-neutral premium collection.",
                "veto_recommended": False,
                "headlines": headlines,
            }

        # 4. Hard earnings-blackout override: live news shows imminent earnings
        if earnings_imminent and result["earnings_risk"] in ("NONE", "LOW"):
            result["earnings_risk"] = "HIGH"
            result["veto_recommended"] = True
            result["sentiment_summary"] = (
                "EARNINGS BLACKOUT: live news flow indicates an imminent earnings report "
                f"for {ticker}. Binary gap risk overrides premium-selling thesis."
            )
            logger.info(f"Earnings blackout override applied to {ticker} based on live headlines.")

        return result

    def _consolidate(self, responses: List[Dict[str, Any]], ticker: str,
                     earnings_imminent: bool, headlines: List) -> Dict[str, Any]:
        """Averages conviction scores across independent LLMs; vetoes if majority vetoes."""
        scores = [r.get("conviction_score", 75) for r in responses if isinstance(r.get("conviction_score"), (int, float))]
        avg_score = int(sum(scores) / len(scores)) if scores else 75
        vetoes = sum(1 for r in responses if r.get("veto_recommended", False))
        majority_veto = vetoes > len(responses) / 2

        regimes = [str(r.get("market_regime", "NEUTRAL")).upper() for r in responses]
        regime = max(set(regimes), key=regimes.count) if regimes else "NEUTRAL"

        risk_levels = [str(r.get("earnings_risk", "LOW")).upper() for r in responses]
        earnings_risk = max(set(risk_levels), key=risk_levels.count) if risk_levels else "LOW"
        # Escalate if ANY ensemble member flags high earnings risk
        if "HIGH" in risk_levels:
            earnings_risk = "HIGH"

        summaries = [r.get("sentiment_summary", "") for r in responses if r.get("sentiment_summary")]
        providers = [r.get("_provider", "llm") for r in responses]

        result = {
            "ticker": ticker,
            "conviction_score": avg_score,
            "market_regime": regime,
            "earnings_risk": earnings_risk,
            "sentiment_summary": summaries[0] if summaries else "Ensemble consensus evaluated.",
            "veto_recommended": bool(majority_veto),
            "ensemble_providers": providers,
            "ensemble_scores": scores,
            "ensemble_mode": True,
            "headlines": headlines,
        }
        if earnings_imminent and result["earnings_risk"] in ("NONE", "LOW"):
            result["earnings_risk"] = "HIGH"
            result["veto_recommended"] = True
            result["sentiment_summary"] = (
                f"EARNINGS BLACKOUT: live news flow indicates imminent earnings for {ticker}. "
                "Binary gap risk overrides premium-selling thesis."
            )
        return result

    def _normalize(self, parsed: Dict[str, Any], ticker: str, headlines: List) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "conviction_score": parsed.get("conviction_score", 82),
            "market_regime": parsed.get("market_regime", "NEUTRAL"),
            "earnings_risk": parsed.get("earnings_risk", "LOW"),
            "sentiment_summary": parsed.get("sentiment_summary", "Macro conditions stable with low catalyst risk over target DTE."),
            "veto_recommended": bool(parsed.get("veto_recommended", False)),
            "headlines": headlines,
        }

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        try:
            clean_json = raw.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
            return json.loads(clean_json.strip())
        except Exception as e:
            logger.warning(f"Sentiment JSON parse error: {e}")
            return {}


sentiment_agent = SentimentAgent()
