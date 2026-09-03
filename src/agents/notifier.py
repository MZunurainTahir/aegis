"""
AEGIS Notification Engine — Telegram Alert Integration
========================================================
Sends real-time trade, veto, hedge, and performance alerts to a Telegram
channel/chat. Optional: activates only when TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID are configured in .env. Zero impact when disabled.
"""
import logging
from typing import Optional
import requests

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger("Aegis.Notifier")


class Notifier:
    """Telegram-based institutional alerting."""

    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, message: str) -> bool:
        """Sends a text message (markdown supported). Fails silently."""
        if not self.enabled:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            resp = requests.post(url, json=payload, timeout=8)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Convenience alert builders
    # ------------------------------------------------------------------
    def notify_trade_executed(self, ticker: str, strategy: str, strike: float,
                              credit: float, annualized_yield: float) -> Optional[bool]:
        return self.send(
            f"🟢 *AEGIS TRADE EXECUTED*\n"
            f"`{strategy.replace('_', ' ')}` — *{ticker}* @ ${strike:.2f}\n"
            f"Credit: `${credit:.2f}` | Ann. Yield: `{annualized_yield:.1f}%`"
        )

    def notify_trade_vetoed(self, ticker: str, strategy: str, verdict: str) -> Optional[bool]:
        return self.send(
            f"🔴 *AEGIS TRADE VETOED*\n"
            f"`{strategy.replace('_', ' ')}` — *{ticker}*\n"
            f"Verdict: `{verdict}`"
        )

    def notify_position_closed(self, ticker: str, action: str, pnl: float) -> Optional[bool]:
        emoji = "🟢" if pnl >= 0 else "🔻"
        return self.send(
            f"{emoji} *AEGIS POSITION CLOSED*\n"
            f"Action: `{action}` — *{ticker}*\n"
            f"Realized P&L: `${pnl:+,.2f}`"
        )

    def notify_hedge(self, contract: str, strike: float, reason: str) -> Optional[bool]:
        return self.send(
            f"🛡️ *AEGIS TAIL HEDGE DEPLOYED*\n"
            f"BUY `{contract}` @ ${strike:.0f}\n"
            f"Trigger: {reason}"
        )

    def notify_cycle_summary(self, equity: float, executed: int, vetoed: int,
                             managed: int, realized: float) -> Optional[bool]:
        return self.send(
            f"⚡ *AEGIS CYCLE COMPLETE*\n"
            f"Equity: `${equity:,.2f}`\n"
            f"New: {executed} | Vetoes: {vetoed} | Managed: {managed}\n"
            f"Realized this cycle: `${realized:+,.2f}`"
        )


notifier = Notifier()
