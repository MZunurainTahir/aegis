"""
AEGIS Portfolio Manager Agent — Autonomous Position Lifecycle Engine
====================================================================
The closing side of the Wheel. This agent continuously manages every open
short option position and executes the institutional management rules that
convert theta decay into REALIZED P&L:

1. PROFIT TAKE  — buy-to-close when option decays to 50% of entry premium
2. STOP LOSS    — buy-to-close when option doubles against us (200%)
3. EXPIRY SWEEP — close positions on their final trading day (capture value,
                  avoid assignment ambiguity)
4. ITM ROLL     — if short put goes in-the-money near expiry, close it and
                  let the Quant Agent re-enter at a lower strike (classic roll-down)

Every action is journaled to SQLite with realized P&L attribution.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.config import RISK_RULES
from src.alpaca_client.alpaca_service import alpaca_service, parse_option_symbol
from src.persistence.database import journal

logger = logging.getLogger("Aegis.PortfolioManager")


class PortfolioManagerAgent:
    """Autonomous open-position management & P&L realization engine."""

    def __init__(self):
        self.alpaca = alpaca_service
        self.journal = journal

    def manage_open_positions(self, log_fn=None) -> Dict[str, Any]:
        """
        Runs a full management sweep over open SHORT option positions.
        Returns a summary of actions taken with realized P&L.
        """
        def log(stage, agent, msg, details=None):
            if log_fn:
                log_fn(stage, agent, msg, details)
            else:
                logger.info(f"{stage}: {msg}")

        log("MANAGEMENT", "PortfolioManager", "Sweeping open positions for profit-take, stop-loss, roll & expiry events...")

        positions = self.alpaca.get_positions()
        option_positions = [p for p in positions if parse_option_symbol(p["symbol"]) and p["qty"] < 0]

        if not option_positions:
            log("MANAGEMENT", "PortfolioManager", "No open short option positions to manage.")
            return {"managed": 0, "actions": [], "realized_pnl": 0.0}

        quotes = self.alpaca.get_option_quotes([p["symbol"] for p in option_positions])
        actions: List[Dict[str, Any]] = []
        realized_total = 0.0

        for pos in option_positions:
            symbol = pos["symbol"]
            parsed = parse_option_symbol(symbol)
            if not parsed:
                continue

            qty = abs(int(pos["qty"])) if pos["qty"] else 1
            entry_premium = abs(pos.get("avg_entry_price") or 0.0)
            mark = quotes.get(symbol, {}).get("mid") or quotes.get(symbol, {}).get("bid") or 0.0

            if entry_premium <= 0:
                continue

            now = datetime.now(timezone.utc)
            dte = (parsed["expiration_dt"] - now).days
            spot = self.alpaca.get_spot_price(parsed["underlying"])

            # -----------------------------------------------------------
            # RULE 1: FINAL-DAY EXPIRY SWEEP
            # -----------------------------------------------------------
            if dte <= 0:
                if mark >= 0.05:
                    res = self._close(symbol, qty, mark, "EXPIRY_SWEEP", parsed, actions, log)
                    if res:
                        realized_total += res
                else:
                    # Worthless: journal it as expired (full premium kept)
                    closed = self.journal.record_trade_close(symbol, 0.01, qty, status="EXPIRED")
                    if closed:
                        realized_total += closed["realized_pnl"]
                        actions.append({**closed, "action": "EXPIRED_WORTHLESS"})
                        log("MANAGEMENT", "PortfolioManager",
                            f"{symbol} expired worthless — 100% premium captured. "
                            f"Realized: ${closed['realized_pnl']:.2f}")
                continue

            # -----------------------------------------------------------
            # RULE 2: TAKE PROFIT at <= 50% of entry premium
            # -----------------------------------------------------------
            if 0 < mark <= entry_premium * RISK_RULES["PROFIT_TAKE_PCT"] and mark >= 0.05:
                res = self._close(symbol, qty, mark, "PROFIT_TAKE", parsed, actions, log,
                                  reason=f"Decayed to {mark:.2f} ({round(mark/entry_premium*100)}% of entry)")
                if res:
                    realized_total += res
                continue

            # -----------------------------------------------------------
            # RULE 3: STOP LOSS at >= 200% of entry premium
            # -----------------------------------------------------------
            if mark >= entry_premium * RISK_RULES["STOP_LOSS_PCT"]:
                res = self._close(symbol, qty, mark, "STOP_LOSS", parsed, actions, log,
                                  reason=f"Adverse move: premium doubled to {mark:.2f}")
                if res:
                    realized_total += res
                continue

            # -----------------------------------------------------------
            # RULE 4: ITM ROLL (DTE <= 5 and strike breached)
            # -----------------------------------------------------------
            is_put = parsed["option_type"] == "put"
            itm = spot < parsed["strike"] if is_put else spot > parsed["strike"]
            if dte <= 5 and itm and mark >= 0.10:
                res = self._close(symbol, qty, mark, "ITM_ROLL", parsed, actions, log,
                                  reason=f"ITM near expiry (spot {spot:.2f} vs strike {parsed['strike']}) — closing for roll")
                if res:
                    realized_total += res
                # Quant Agent will naturally re-enter next screening phase
                continue

        summary = {
            "managed": len(actions),
            "actions": actions,
            "realized_pnl": round(realized_total, 2),
            "open_short_options": len(option_positions),
        }
        if actions:
            log("MANAGEMENT_COMPLETE", "PortfolioManager",
                f"Executed {len(actions)} management actions | Realized P&L: ${realized_total:.2f}",
                {"actions": [a.get("action") for a in actions]})
        else:
            log("MANAGEMENT_COMPLETE", "PortfolioManager",
                f"All {len(option_positions)} open positions healthy — no management actions required.")
        return summary

    def _close(self, symbol: str, qty: int, mark: float, action: str,
               parsed: Dict[str, Any], actions: List, log_fn, reason: str = "") -> Optional[float]:
        """Executes buy-to-close and journals the realized P&L."""
        order = self.alpaca.close_option_position(symbol, qty=qty)
        if not order.get("success"):
            logger.error(f"Failed to close {symbol}: {order.get('error')}")
            return None

        closed = self.journal.record_trade_close(symbol, mark, qty, status="CLOSED")
        pnl = closed["realized_pnl"] if closed else 0.0
        record = {
            "action": action,
            "contract_symbol": symbol,
            "ticker": parsed["underlying"],
            "qty": qty,
            "exit_price": mark,
            "realized_pnl": pnl,
            "order_id": order.get("order_id"),
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        actions.append(record)
        if closed:
            actions[-1].update({"entry_premium": closed.get("entry_premium")})

        log_fn("POSITION_CLOSED", "PortfolioManager",
               f"[{action}] Buy-to-close {qty}x {symbol} @ ${mark:.2f}. "
               f"Realized P&L: ${pnl:+.2f}. {reason}".strip(), record)
        return pnl

    def get_open_position_marks(self) -> List[Dict[str, Any]]:
        """Returns open option positions marked to market with management state."""
        positions = self.alpaca.get_positions()
        opt_positions = [p for p in positions if parse_option_symbol(p["symbol"])]
        quotes = self.alpaca.get_option_quotes([p["symbol"] for p in opt_positions]) if opt_positions else {}
        marks = []
        now = datetime.now(timezone.utc)
        for p in opt_positions:
            parsed = parse_option_symbol(p["symbol"])
            q = quotes.get(p["symbol"], {})
            entry = abs(p.get("avg_entry_price") or 0.0)
            mark = q.get("mid") or q.get("bid") or 0.0
            dte = (parsed["expiration_dt"] - now).days if parsed else 0
            state = "HOLD"
            if entry > 0:
                if 0 < mark <= entry * RISK_RULES["PROFIT_TAKE_PCT"]:
                    state = "PROFIT_TAKE_DUE"
                elif mark >= entry * RISK_RULES["STOP_LOSS_PCT"]:
                    state = "STOP_LOSS_DUE"
                elif dte <= 0:
                    state = "EXPIRY_TODAY"
                elif dte <= 5:
                    state = "ROLL_WINDOW"
            marks.append({
                "contract_symbol": p["symbol"],
                "ticker": parsed["underlying"] if parsed else p["symbol"],
                "option_type": parsed["option_type"] if parsed else "",
                "strike": parsed["strike"] if parsed else None,
                "expiration": parsed["expiration"] if parsed else "",
                "dte": dte,
                "qty": p["qty"],
                "entry_premium": entry,
                "current_mark": mark,
                "pnl_pct": round((1 - mark / entry) * 100, 1) if entry > 0 else 0.0,
                "management_state": state,
                "delta": q.get("delta"),
                "theta": q.get("theta"),
            })
        return marks


portfolio_manager = PortfolioManagerAgent()
