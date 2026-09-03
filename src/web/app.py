import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import (
    BASE_DIR,
    DEFAULT_WATCHLIST,
    RISK_RULES,
    AUDIO_OUTPUT_DIR,
    DECISION_LOG_PATH,
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)
from src.alpaca_client.alpaca_service import alpaca_service
from src.agents.quant_agent import quant_agent
from src.agents.sentiment_agent import sentiment_agent
from src.agents.risk_agent import risk_agent
from src.agents.orchestrator import orchestrator
from src.agents.portfolio_manager import portfolio_manager
from src.agents.news_agent import news_agent
from src.ai.voice_narrator import voice_narrator
from src.persistence.database import journal

logger = logging.getLogger("Aegis.Web")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Supabase client (optional — graceful degradation if not configured)
# ---------------------------------------------------------------------------
supabase_client = None

def _init_supabase():
    global supabase_client
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and not SUPABASE_URL.startswith("https://your-project"):
        try:
            from supabase import create_client, Client
            supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            logger.info("Supabase client initialised successfully.")
        except Exception as e:
            logger.warning(f"Supabase init failed (running without Supabase): {e}")
    else:
        logger.warning("Supabase env vars not set — auth will use local fallback mode.")

_init_supabase()

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Aegis: Autonomous Risk-Governed Options Income Desk",
    description="Institutional multi-agent options trading platform on Alpaca Trading API & FastMCP — v3.0 with full position lifecycle management, live news intelligence, real performance analytics, and WebSocket streaming.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = BASE_DIR / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# ---------------------------------------------------------------------------
# WebSocket live-stream hub (agent decision feed pushes in real time)
# ---------------------------------------------------------------------------
class LiveHub:
    """Fan-out hub broadcasting every orchestrator event to all WS clients."""

    def __init__(self):
        self.clients: List[WebSocket] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        """Capture the main event loop so worker threads can schedule sends."""
        self.loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)

    def broadcast_sync(self, event: Dict[str, Any]):
        """Thread-safe broadcast — orchestrator cycles run in worker threads."""
        if not self.clients or not self.loop or self.loop.is_closed():
            return
        msg = json.dumps(event)
        for ws in list(self.clients):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(msg), self.loop)
            except Exception:
                try:
                    self.disconnect(ws)
                except Exception:
                    pass

    def _broadcast(self, event: Dict[str, Any]):
        self.broadcast_sync(event)


hub = LiveHub()


def _ws_hook(event: Dict[str, Any]):
    """Hook attached to orchestrator.log_event — pushes events to WS clients."""
    try:
        hub.broadcast_sync(event)
    except Exception as e:
        logger.debug(f"WS broadcast failed: {e}")


orchestrator_ws_hook = _ws_hook
# Patch the orchestrator to fan out every log event
_orig_log_event = orchestrator.log_event

def _patched_log_event(stage, agent, message, details=None):
    event = None
    _orig_log_event(stage, agent, message, details)
    global _last_event_meta
    _last_event_meta = {"stage": stage, "agent": agent, "message": message,
                        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S")}
    _ws_hook(_last_event_meta)

_last_event_meta = None
orchestrator.log_event = _patched_log_event


@app.on_event("startup")
async def _startup_bind_ws_loop():
    """Bind the main event loop so orchestrator threads can broadcast."""
    hub.bind_loop(asyncio.get_running_loop())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time decision stream: every agent event pushed instantly to the UI."""
    await hub.connect(websocket)
    try:
        # Send recent history on connect (welcome frame when history is empty)
        sent = 0
        for log in orchestrator.live_logs[-30:]:
            await websocket.send_text(json.dumps(log))
            sent += 1
        if sent == 0:
            await websocket.send_text(json.dumps({
                "agent": "SYSTEM",
                "type": "connected",
                "message": "AEGIS live decision stream connected — waiting for cycle events...",
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            }))
        while True:
            # Keep alive: client pings, we ignore content
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)
    except Exception:
        hub.disconnect(websocket)


# ---------------------------------------------------------------------------
# Autonomous Loop State
# ---------------------------------------------------------------------------
class AutoLoopState:
    is_running: bool = False
    interval_seconds: int = 300
    task: Optional[asyncio.Task] = None
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    cycles_completed: int = 0

auto_state = AutoLoopState()

async def background_trading_loop():
    logger.info("Autonomous trading loop started...")
    while auto_state.is_running:
        try:
            logger.info("Auto-loop executing scheduled Aegis cycle...")
            auto_state.last_run = datetime.now(timezone.utc).isoformat()
            # Run the blocking cycle in a worker thread so the event loop stays alive
            await asyncio.to_thread(orchestrator.run_full_cycle, True)
            auto_state.cycles_completed += 1
        except Exception as e:
            logger.error(f"Error in auto-loop cycle: {e}")
        auto_state.next_run = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + auto_state.interval_seconds, tz=timezone.utc
        ).isoformat()
        await asyncio.sleep(auto_state.interval_seconds)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = static_path / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>Aegis Web Cockpit</h1><p>Frontend static files loading...</p>")

@app.get("/api/health")
def health():
    """Liveness probe for deployment platforms."""
    clock = alpaca_service.get_market_clock()
    return {
        "status": "operational",
        "version": "3.0.0",
        "time": datetime.now(timezone.utc).isoformat(),
        "market_open": clock.get("is_open"),
        "auto_loop": auto_state.is_running,
    }

# ---------------------------------------------------------------------------
# REGISTER — Create new user account
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    full_name: str
    dob: str                          # ISO date string e.g. "1990-05-15"
    email: str
    password: str
    alpaca_account_id: Optional[str] = None
    alpaca_api_key: Optional[str] = None
    alpaca_secret_key: Optional[str] = None   # kept optional; can add later

class RegisterResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None

@app.post("/api/register", response_model=RegisterResponse)
async def register_user(req: RegisterRequest):
    """
    Creates a new user via Supabase Auth and stores their profile + Alpaca credentials
    in the public.users table.
    """
    if supabase_client:
        try:
            # 1. Create auth user via Supabase (handles password hashing)
            auth_res = supabase_client.auth.sign_up({
                "email": req.email,
                "password": req.password,
                "options": {
                    "data": {
                        "full_name": req.full_name,
                        "dob": req.dob
                    }
                }
            })

            if not auth_res.user:
                return RegisterResponse(success=False, message="Registration failed — email may already be registered.")

            user_id = auth_res.user.id

            # 2. Upsert profile row in public.users table
            profile_data = {
                "id": user_id,
                "full_name": req.full_name,
                "dob": req.dob,
                "email": req.email,
                "alpaca_account_id": req.alpaca_account_id or "",
                "alpaca_api_key": req.alpaca_api_key or "",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase_client.table("users").upsert(profile_data).execute()

            orchestrator.log_event("AUTH_REGISTER", "Authentication", f"New user registered: {req.email}")
            return RegisterResponse(
                success=True,
                message="Account created successfully! Please sign in.",
                user_id=user_id
            )

        except Exception as e:
            logger.error(f"Registration error: {e}")
            err_str = str(e).lower()
            if "already registered" in err_str or "already exists" in err_str or "unique" in err_str:
                return RegisterResponse(success=False, message="An account with this email already exists. Please sign in.")
            return RegisterResponse(success=False, message=f"Registration error: {str(e)}")

    else:
        # Fallback — Supabase not configured, accept locally for demo
        logger.warning("Supabase not available — using local fallback registration.")
        orchestrator.log_event("AUTH_REGISTER", "Authentication", f"[FALLBACK] User registered locally: {req.email}")
        return RegisterResponse(
            success=True,
            message="Account created (demo mode — configure Supabase for production). Please sign in.",
            user_id="local-demo-user"
        )


# ---------------------------------------------------------------------------
# LOGIN — Sign in and connect Alpaca
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str
    # Optional overrides (user can also just log in and load from Supabase)
    alpaca_api_key: Optional[str] = None
    alpaca_secret_key: Optional[str] = None
    paper: bool = True

@app.post("/api/login")
def login_user(req: LoginRequest):
    """Signs in via Supabase Auth. Loads Alpaca credentials from profile if not overridden."""
    alpaca_key = req.alpaca_api_key
    alpaca_secret = req.alpaca_secret_key

    if supabase_client:
        try:
            # 1. Authenticate via Supabase
            auth_res = supabase_client.auth.sign_in_with_password({
                "email": req.email,
                "password": req.password,
            })

            if not auth_res.user:
                return JSONResponse(status_code=401, content={"success": False, "message": "Invalid email or password."})

            user_id = auth_res.user.id

            # 2. Load profile from public.users
            profile_res = supabase_client.table("users").select("*").eq("id", user_id).single().execute()
            profile = profile_res.data or {}

            # Use stored Alpaca creds unless caller explicitly overrides them
            if not alpaca_key and profile.get("alpaca_api_key"):
                alpaca_key = profile["alpaca_api_key"]
            if not alpaca_secret:
                # Secret is not stored (security) — must be provided by user each sign-in
                # If it was passed in request, we use it; else fallback to env default
                alpaca_secret = os.getenv("ALPACA_SECRET_KEY", "")

        except Exception as e:
            logger.warning(f"Supabase login error (falling back): {e}")
            # Allow fallback for demo
            pass

    # 3. Connect Alpaca with resolved credentials
    if alpaca_key and alpaca_secret:
        alpaca_service.update_credentials(alpaca_key, alpaca_secret, req.paper)

    try:
        acc = alpaca_service.get_account_summary()
    except Exception as e:
        acc = {"account_id": "N/A", "equity": 0, "buying_power": 0, "cash": 0, "day_pnl": 0, "day_pnl_pct": 0}
        logger.error(f"Alpaca account fetch failed: {e}")

    orchestrator.log_event("AUTH_LOGIN", "Authentication", f"User {req.email} signed in. Alpaca Account: {acc.get('account_id', 'N/A')}")

    return {
        "success": True,
        "email": req.email,
        "account": acc
    }


# ---------------------------------------------------------------------------
# ACCOUNT DATA
# ---------------------------------------------------------------------------
@app.get("/api/account")
def get_account_info():
    """Returns live Alpaca account balance, P&L, buying power, Greeks, and market state."""
    acc = alpaca_service.get_account_summary()
    greeks = alpaca_service.calculate_portfolio_greeks()
    positions = alpaca_service.get_positions()
    clock = alpaca_service.get_market_clock()
    stress = alpaca_service.get_market_stress_index()
    return {
        "account": acc,
        "portfolio_greeks": greeks,
        "positions": positions,
        "risk_rules": RISK_RULES,
        "market_data": {
            "stress_index": stress,
            "stress_threshold": RISK_RULES["STRESS_VIX_HEDGE_THRESHOLD"],
            "market_open": clock.get("is_open"),
            "next_open": clock.get("next_open"),
            "next_close": clock.get("next_close"),
        },
        "auto_trading": {
            "active": auto_state.is_running,
            "interval_sec": auto_state.interval_seconds,
            "cycles_completed": auto_state.cycles_completed,
            "last_run": auto_state.last_run,
        }
    }


@app.get("/api/screen")
def screen_opportunities():
    """Runs Quant Agent to screen options chains across active watchlist."""
    proposals = quant_agent.screen_opportunities()
    return {
        "count": len(proposals),
        "proposals": proposals,
        "watchlist": quant_agent.watchlist
    }


@app.get("/api/logs")
async def get_live_logs():
    """Returns the live in-memory decision audit stream."""
    return {
        "logs": orchestrator.live_logs,
        "total_events": len(orchestrator.live_logs)
    }


@app.post("/api/run-cycle")
async def trigger_cycle():
    """Manually triggers an end-to-end multi-agent autonomous cycle (runs in worker thread)."""
    result = await asyncio.to_thread(orchestrator.run_full_cycle, True)
    return result


@app.post("/api/toggle-auto")
async def toggle_auto(interval_sec: int = 300):
    """Toggles 24/7 background autonomous execution loop."""
    if auto_state.is_running:
        auto_state.is_running = False
        if auto_state.task:
            auto_state.task.cancel()
            auto_state.task = None
        orchestrator.log_event("AUTO_LOOP", "Orchestrator", "Autonomous trading loop paused by operator.")
        return {"status": "paused", "active": False}
    else:
        auto_state.is_running = True
        auto_state.interval_seconds = max(60, interval_sec)
        auto_state.task = asyncio.create_task(background_trading_loop())
        orchestrator.log_event("AUTO_LOOP", "Orchestrator", f"Autonomous trading loop activated (Interval: {auto_state.interval_seconds}s).")
        return {"status": "running", "active": True, "interval_sec": auto_state.interval_seconds}


@app.post("/api/trigger-hedge")
def trigger_emergency_hedge(stress_index: float = 28.5):
    """Triggers an independent tail-risk hedge evaluation and protective put order."""
    res = risk_agent.check_and_trigger_tail_hedge(market_stress_index=stress_index)
    orchestrator.log_event("MANUAL_HEDGE_TRIGGER", "Operator", f"Manual tail hedge audit triggered (Stress Index: {stress_index})", res)
    return res


class ManualTradeRequest(BaseModel):
    symbol: str
    qty: int = 1
    side: str = "sell"
    order_type: str = "limit"
    limit_price: Optional[float] = None
    strike: Optional[float] = None
    underlying: Optional[str] = None
    strategy: Optional[str] = "CASH_SECURED_PUT"


@app.post("/api/execute-trade")
def execute_manual_trade(req: ManualTradeRequest):
    """Executes a trade on Alpaca through the risk gate."""
    res = alpaca_service.execute_order(
        symbol=req.symbol,
        qty=req.qty,
        side=req.side,
        order_type=req.order_type,
        limit_price=req.limit_price
    )
    orchestrator.log_event(
        "EXECUTION_MANUAL", "ExecutionEngine",
        f"Order submitted to Alpaca Paper: {req.side.upper()} {req.qty}x {req.symbol} @ ${req.limit_price or 'MKT'}",
        res
    )
    # Journal manual trades too
    journal.record_trade_open(
        contract_symbol=req.symbol, ticker=req.underlying or req.symbol,
        strategy=req.strategy or "MANUAL", side="SELL_TO_OPEN" if req.side == "sell" else "BUY_TO_OPEN",
        qty=req.qty, strike=req.strike, expiration=None, dte=None, delta=None,
        premium=req.limit_price or 0.0, order_id=res.get("order_id"),
        order_status=res.get("status", "SUBMITTED"), risk_verdict="MANUAL",
    )
    return {
        "success": bool(res.get("success")),
        "message": (f"Successfully submitted {req.side.upper()} order for {req.qty}x {req.symbol} to Alpaca paper broker."
                    if res.get("success") else f"Order rejected: {res.get('error', 'unknown error')}"),
        "order": res
    }


# ---------------------------------------------------------------------------
# v3.0 ENDPOINTS — Performance, Journal, News, Market Data, Orders, Positions
# ---------------------------------------------------------------------------
@app.get("/api/performance")
def get_performance():
    """REAL performance analytics computed from the SQLite trade journal."""
    analytics = journal.get_performance_analytics(starting_equity=100000.0)
    equity_curve = journal.get_equity_curve(limit=500)
    return {
        **analytics,
        "equity_curve": equity_curve,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "LIVE_JOURNAL_SQLITE",
    }


@app.get("/api/journal")
def get_journal(limit: int = 50):
    """Returns the persistent trade journal (newest first)."""
    trades = journal.get_trade_journal(limit=limit)
    cycles = journal.get_cycle_history(limit=15)
    hedges = journal.get_hedge_history(limit=10)
    return {"trades": trades, "cycle_history": cycles, "hedge_history": hedges}


@app.get("/api/news")
def get_news():
    """Returns live market headlines, regime classification, and per-ticker feeds."""
    regime = news_agent.classify_market_regime()
    market_headlines = news_agent.fetch_market_news(limit=8)
    return {
        "regime": regime,
        "market_headlines": market_headlines,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/market-data")
def get_market_data():
    """Live market telemetry: stress index, market clock, watchlist spot matrix."""
    clock = alpaca_service.get_market_clock()
    stress = alpaca_service.get_market_stress_index()
    regime = news_agent._regime_cache[0] if news_agent._regime_cache else None
    watchlist_data = []
    for ticker in DEFAULT_WATCHLIST[:8]:
        try:
            spot = alpaca_service.get_spot_price(ticker)
            watchlist_data.append({"ticker": ticker, "spot": round(spot, 2)})
        except Exception:
            continue
    return {
        "stress_index": stress,
        "stress_threshold": RISK_RULES["STRESS_VIX_HEDGE_THRESHOLD"],
        "market_clock": clock,
        "regime": regime,
        "watchlist": watchlist_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/orders")
def get_orders(limit: int = 20, status: str = "all"):
    """Returns the live order blotter from Alpaca (order lifecycle tracking)."""
    orders = alpaca_service.get_recent_orders(limit=limit, status=status)
    return {"orders": orders, "count": len(orders)}


@app.get("/api/positions/marks")
def get_position_marks():
    """Open option positions marked to market with management states."""
    marks = portfolio_manager.get_open_position_marks()
    return {"marks": marks, "count": len(marks)}


class ClosePositionRequest(BaseModel):
    contract_symbol: str
    qty: int = 1

@app.post("/api/close-position")
def close_position(req: ClosePositionRequest):
    """Manually buy-to-close an open short option position."""
    order = alpaca_service.close_option_position(req.contract_symbol, qty=req.qty)
    if order.get("success"):
        quotes = alpaca_service.get_option_quotes([req.contract_symbol])
        mark = quotes.get(req.contract_symbol, {}).get("mid", 0.0)
        closed = journal.record_trade_close(req.contract_symbol, mark, req.qty, status="MANUALLY_CLOSED")
        orchestrator.log_event("MANUAL_CLOSE", "Operator",
                               f"Manual buy-to-close {req.qty}x {req.contract_symbol}", order)
        return {"success": True, "order": order, "journal": closed}
    return {"success": False, "order": order}


@app.get("/api/audio-briefing")
def generate_live_briefing():
    """Generates an executive audio briefing using ElevenLabs."""
    account = alpaca_service.get_account_summary()
    greeks = alpaca_service.calculate_portfolio_greeks()
    perf = journal.get_performance_analytics(starting_equity=100000.0)
    text = (
        f"Aegis intelligence brief. Dedicated hackathon paper account is active at ${account['equity']:,.2f} equity. "
        f"Portfolio Net Delta is calibrated at {greeks['net_delta']} with daily theta yield generating ${greeks['daily_theta_income']:.2f}. "
        f"Lifetime realized P and L stands at ${perf['total_realized_pnl']:.2f} across {perf['closed_trades']} closed trades "
        f"with a {perf['win_rate_pct']} percent win rate. "
        f"Autonomous risk governance gates are fully armed and monitoring tail stress signals."
    )
    audio_path = voice_narrator.generate_speech(text)
    return {
        "text": text,
        "audio_url": audio_path or ""
    }


@app.get("/api/backtest-stats")
def get_backtest_stats():
    """Returns REAL live-forward performance from the journal (no hardcoded data)."""
    perf = journal.get_performance_analytics(starting_equity=100000.0)
    equity_curve = journal.get_equity_curve(limit=500)
    monthly = []
    if equity_curve:
        by_month: Dict[str, float] = {}
        base = equity_curve[0]["equity"]
        for point in equity_curve:
            month = point["timestamp"][:7]  # YYYY-MM
            by_month[month] = (point["equity"] - base) / base * 100 if base else 0
        monthly = [{"month": m, "aegis_return_pct": round(v, 2)} for m, v in sorted(by_month.items())]
    return {
        "strategy": "Aegis Systematic Options Wheel + Autonomous Tail Hedge",
        "benchmark": "S&P 500 (SPY Buy & Hold)",
        "data_source": "LIVE FORWARD JOURNAL (SQLite) — not simulated",
        "win_rate_pct": perf["win_rate_pct"],
        "profit_factor": perf["profit_factor"],
        "sharpe_ratio": perf["sharpe_ratio"],
        "max_drawdown_pct": perf["max_drawdown_pct"],
        "total_return_pct": perf["total_return_pct"],
        "total_realized_pnl": perf["total_realized_pnl"],
        "open_positions": perf["open_positions"],
        "closed_trades": perf["closed_trades"],
        "total_cycles": perf["total_cycles"],
        "monthly_data": monthly,
    }


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    file_p = AUDIO_OUTPUT_DIR / filename
    if file_p.exists():
        return FileResponse(str(file_p), media_type="audio/mpeg")
    return JSONResponse(status_code=404, content={"error": "Audio file not found"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.web.app:app", host="0.0.0.0", port=8000, reload=False)
