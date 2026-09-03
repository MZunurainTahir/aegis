"""
AEGIS News & Market Regime Agent — Real-World Information Ingestion
====================================================================
Bridges the gap between LLM training data and the live market by ingesting
REAL news headlines via Google News RSS (no API key required, stdlib XML
parsing) and distilling them through the multi-LLM ensemble into:

1. A live MARKET REGIME classification (RISK_ON / NEUTRAL / RISK_OFF / CRISIS)
2. Per-ticker headline feeds for the Sentiment Agent's grounded analysis
3. Earnings-season proximity warnings for the blackout gate

Headlines are cached for 10 minutes to respect rate limits.
"""
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests

from src.ai.llm_manager import llm_manager

logger = logging.getLogger("Aegis.NewsAgent")

RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
CACHE_TTL = 600.0  # 10 minutes


class NewsAgent:
    """Live news ingestion + LLM regime classification."""

    def __init__(self):
        self.llm = llm_manager
        self._cache: Dict[str, tuple] = {}  # query -> (headlines, timestamp)
        self._regime_cache: Optional[tuple] = None  # (regime_dict, timestamp)

    # ------------------------------------------------------------------
    # RSS ingestion
    # ------------------------------------------------------------------
    def fetch_headlines(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Fetches live news headlines for a query from Google News RSS."""
        cache_key = query.lower().strip()
        now = time.time()
        if cache_key in self._cache:
            cached, ts = self._cache[cache_key]
            if now - ts < CACHE_TTL:
                return cached

        headlines: List[Dict[str, Any]] = []
        try:
            url = RSS_URL.format(query=requests.utils.quote(query))
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 (Aegis Trading Desk)"})
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.iter("item"):
                    title = (item.findtext("title") or "").strip()
                    pub = (item.findtext("pubDate") or "").strip()
                    source = ""
                    src_el = item.find("source")
                    if src_el is not None:
                        source = (src_el.text or "").strip()
                    if title:
                        # Clean Google News suffix "- Publisher"
                        clean = re.sub(r"\s+-\s+[^-]+$", "", title)
                        headlines.append({"title": clean, "source": source, "published": pub})
                    if len(headlines) >= limit:
                        break
        except Exception as e:
            logger.warning(f"News RSS fetch failed for '{query}': {e}")

        self._cache[cache_key] = (headlines, now)
        return headlines

    def fetch_ticker_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.fetch_headlines(f"{ticker} stock", limit=limit)

    def fetch_market_news(self, limit: int = 6) -> List[Dict[str, Any]]:
        return self.fetch_headlines("stock market today Federal Reserve economy", limit=limit)

    # ------------------------------------------------------------------
    # Market regime classification (once per cycle)
    # ------------------------------------------------------------------
    def classify_market_regime(self) -> Dict[str, Any]:
        """
        Single LLM call per cycle using REAL market headlines.
        Returns regime, conviction, guidance for premium selling.
        """
        now = time.time()
        if self._regime_cache and now - self._regime_cache[1] < CACHE_TTL:
            return self._regime_cache[0]

        headlines = self.fetch_market_news()
        headline_text = "\n".join(f"- {h['title']} ({h['source']})" for h in headlines) or "- (no live headlines available)"

        system_prompt = (
            "You are the Aegis Market Regime Classifier on an institutional options desk. "
            "Classify today's market regime using ONLY the live headlines provided. "
            "Output MUST be valid JSON:\n"
            "{\n"
            '  "regime": "<RISK_ON | NEUTRAL | RISK_OFF | CRISIS>",\n'
            '  "confidence": <int 1-100>,\n'
            '  "summary": "<one-sentence market overview>",\n'
            '  "premium_selling_favorable": <bool>,\n'
            '  "volatility_expectation": "<ELEVATED | NORMAL | SUPPRESSED>",\n'
            '  "key_risks": ["<risk 1>", "<risk 2>"]\n'
            "}"
        )
        user_prompt = f"Live market headlines right now:\n{headline_text}\n\nClassify the current market regime."

        raw = self.llm.query(system_prompt, user_prompt, json_mode=True)
        parsed = self._safe_json(raw)
        result = {
            "regime": parsed.get("regime", "NEUTRAL"),
            "confidence": int(parsed.get("confidence", 70)),
            "summary": parsed.get("summary", "Live headline ingestion unavailable — defaulting to neutral regime."),
            "premium_selling_favorable": bool(parsed.get("premium_selling_favorable", True)),
            "volatility_expectation": parsed.get("volatility_expectation", "NORMAL"),
            "key_risks": parsed.get("key_risks", []),
            "headlines": headlines,
            "source": "LIVE_NEWS_RSS",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._regime_cache = (result, now)
        return result

    # ------------------------------------------------------------------
    # Earnings proximity detection from headlines
    # ------------------------------------------------------------------
    def detect_earnings_proximity(self, ticker: str) -> Dict[str, Any]:
        """
        Scans live headlines for earnings-report language near this ticker.
        Combined with LLM knowledge cutoff as a conservative blackout gate.
        """
        headlines = self.fetch_ticker_news(ticker, limit=8)
        earnings_pattern = re.compile(
            r"\b(earnings|reports|quarterly results|Q[1-4] results|EPS|guidance|"
            r"reports on|to report|earnings call|after (the )?bell|before (the )?market)\b", re.I
        )
        earnings_mentions = [h["title"] for h in headlines if earnings_pattern.search(h["title"])]

        upcoming_pattern = re.compile(r"\b(this week|next week|tomorrow|tonight|upcoming|monday|tuesday|wednesday|thursday|friday)\b", re.I)
        imminent = [t for t in earnings_mentions if upcoming_pattern.search(t)]

        return {
            "ticker": ticker,
            "earnings_mentions": earnings_mentions[:3],
            "imminent_flag": len(imminent) > 0,
            "headlines": headlines,
        }

    def _safe_json(self, raw: str) -> Dict[str, Any]:
        try:
            clean = raw.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.endswith("```"):
                clean = clean[:-3]
            import json
            return json.loads(clean.strip())
        except Exception:
            return {}


news_agent = NewsAgent()
