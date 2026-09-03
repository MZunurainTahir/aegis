# 🛡️ AEGIS v3.0 — Autonomous, Risk-Governed Options Income Desk

### Alpaca AI Trading Agents Hackathon — LabLab.ai × Alpaca

[![Alpaca Trading API](https://img.shields.io/badge/Alpaca-Trading%20API%20%26%20MCP-blue?style=for-the-badge&logo=alpaca)](https://alpaca.markets)
[![FastMCP Protocol](https://img.shields.io/badge/FastMCP-11%20Tools-emerald?style=for-the-badge)](https://github.com/jlowin/fastmcp)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-yellow?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-WebSocket%20Cockpit-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-Persistent%20Journal-lightgrey?style=for-the-badge&logo=sqlite)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)

---

## 📌 Executive Overview

**AEGIS** is an institutional-grade, **five-agent autonomous options trading platform** built on Alpaca's Trading API. It runs the full Wheel strategy lifecycle — **discover, sell premium, manage, and close** — with zero human intervention:

- **Sells defined-risk premium** (Cash-Secured Puts 0.15–0.30Δ, Covered Calls 0.20–0.35Δ, 7–45 DTE) on liquid blue chips and ETFs (`SPY`, `QQQ`, `AAPL`, `MSFT`, `NVDA`, `AMZN`, …)
- **Manages every open position autonomously**: 50% take-profit, 200% stop-loss, ITM rolls, and expiry-day sweeps
- **Refuses to trade blind**: ingests live news via RSS, classifies the market regime, and enforces earnings blackouts
- **Guards itself with a sovereign Risk Agent** that holds absolute veto power and **actually executes** tail hedges when its real VIX-proxy stress index spikes
- **Journals everything to SQLite** — every order, veto, hedge, equity snapshot, and cycle — and computes real performance analytics (Sharpe, drawdown, profit factor, win rate)

Every number on the dashboard is **real, measured, and auditable**. Nothing is simulated or hardcoded.

---

## 🏛️ Five-Agent Architecture

```
                         ┌──────────────────────────┐
                         │  Google News RSS + SPY   │
                         │  IV (VIX-proxy) Feed     │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │  1. NEWS AGENT           │  Regime: RISK_ON/NEUTRAL/
                         │  Live RSS ingestion      │  RISK_OFF/CRISIS + earnings
                         │  + LLM regime classifier │  blackout detection
                         └────────────┬─────────────┘
                                      ▼
┌───────────────────┐    ┌──────────────────────────┐
│ 2. QUANT AGENT    │    │  5. PORTFOLIO MANAGER    │  (runs FIRST every cycle)
│ IV-rank scoring,  │    │  Take-profit @ 50%,      │  Stop-loss @ 200%,
│ delta targeting,  │    │  ITM rolls, expiry sweep, │  realized P&L journaling
│ duplicate guards  │    │  mark-to-market feeds    │
└─────────┬─────────┘    └────────────┬─────────────┘
          ▼                           ▼
┌───────────────────┐    ┌──────────────────────────┐
│ 3. SENTIMENT AGENT│    │  4. RISK GOVERNANCE AGENT │  Hard limits: ≤10%/trade,
│ Multi-LLM ensemble│───►│  SOVEREIGN VETO POWER     │  ≤20%/ticker, cash reserve,
│ consensus on REAL │    │  + REAL tail-hedge        │  delta gates, stress index
│ live headlines    │    │  execution w/ cooldown    │  > 25 → BUY protective put
└───────────────────┘    └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ 6. ORCHESTRATOR v2       │  Cycle lock, market-hours
                         │  manage-first pipeline   │  guard, SQLite journal,
                         │  + Telegram alerts       │  voice briefings
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ ALPACA PAPER BROKERAGE    │  Real orders. Honest
                         │ (live option quotes +    │  errors. Real P&L.
                         │  real-time Greeks)       │
                         └──────────────────────────┘
```

### The Multi-LLM Ensemble
Sentiment and regime decisions are not left to a single model. The LLM Manager fans out across a **six-provider chain** — Groq (Llama-3.3-70B) → Cerebras → Gemini Flash → DeepSeek → Mistral → OpenRouter — with automatic rate-limit cooldowns, failover, and an **ensemble consensus mode** that averages conviction scores across models.

---

## 🔄 The Autonomous Cycle (Orchestrator v2)

Every cycle, in order:

1. **Market-hours check** — Alpaca market clock; runs management-only audits when closed
2. **Account audit** — live equity, buying power, portfolio Greeks, real stress index
3. **Position management first** — Portfolio Manager sweeps every open short option for take-profit / stop-loss / roll / expiry actions and books realized P&L
4. **Regime classification** — News Agent reads live RSS headlines and classifies the market
5. **Screening** — Quant Agent scores chains by IV-rank-adjusted yield with **duplicate-position guards** and **cash-reserve-aware sizing**
6. **Sentiment gate** — per-ticker news-grounded LLM consensus with **earnings blackout overrides**
7. **Risk governance** — deterministic veto gates on every proposal
8. **Execution** — real Alpaca limit orders (pays the ask for reliable fills); failures are reported honestly, never faked
9. **Tail hedge** — real SPY ATM-IV stress index > 25 → protective put executed with a 20-hour cooldown
10. **Journaling + alerts** — SQLite snapshot, cycle history, Telegram push, optional voice briefing

---

## 🚀 Getting Started

### 1. Clone & Install
```bash
git clone https://github.com/MZunurainTahir/aegis.git
cd aegis
python -m venv venv
venv\Scripts\activate        # Windows  |  source venv/bin/activate  (Linux/macOS)
pip install -r requirements.txt
```

### 2. Configure `.env` (copy from `.env.example`)
```env
# Required
ALPACA_API_KEY=your_paper_key
ALPACA_SECRET_KEY=your_paper_secret
ALPACA_PAPER=true

# At least one LLM provider (more = better consensus)
GROQ_API_KEY=...
CEREBRAS_API_KEY=...
GEMINI_API_KEY=...

# Optional
ELEVENLABS_API_KEY=...        # voice briefings
TELEGRAM_BOT_TOKEN=...        # live trade alerts
TELEGRAM_CHAT_ID=...
```

### 3. Launch the Web Cockpit
```bash
python -m uvicorn src.web.app:app --host 127.0.0.1 --port 8000
```
Open **http://127.0.0.1:8000** — live WebSocket decision stream, performance analytics, trade journal, market monitor, and position marks with one-click close.

---

## 💻 CLI — 10 Headless Commands

```bash
python src/cli.py --status        # equity, Greeks, market clock, stress index
python src/cli.py --screen        # quant screening with IV-rank scoring
python src/cli.py --run-cycle     # full autonomous cycle
python src/cli.py --manage        # portfolio manager sweep (TP/SL/roll/expiry)
python src/cli.py --hedge         # real stress check + tail hedge
python src/cli.py --performance   # real SQLite analytics (Sharpe, DD, win rate)
python src/cli.py --journal       # persistent trade journal
python src/cli.py --news          # live headlines + regime
python src/cli.py --regime        # market regime classification
python src/cli.py --loop 15       # continuous autonomy every 15 minutes
python src/cli.py --json          # any command as JSON (for cron/CI)
```

---

## 🔌 FastMCP Server — 11 Tools for AI Assistants

Let Cursor, Claude, or any MCP client run the desk:

```bash
python src/mcp/fastmcp_server.py
```

| Tool | Purpose |
|---|---|
| `aegis_get_account_and_greeks` | Live account, positions, portfolio Greeks |
| `aegis_screen_wheel_opportunities` | Quant screening results |
| `aegis_evaluate_risk` | Run risk-governance gates on a proposal |
| `aegis_run_trading_cycle` | Execute a full autonomous cycle |
| `aegis_trigger_autonomous_hedge` | Force a tail-hedge evaluation |
| `aegis_get_performance_analytics` | Real journal analytics (Sharpe, PF, DD) |
| `aegis_get_trade_journal` | Persistent trade history |
| `aegis_manage_positions` | Run the Portfolio Manager sweep |
| `aegis_get_market_regime` | Live regime classification |
| `aegis_get_news` | Live RSS headlines |
| `aegis_get_order_blotter` | Recent Alpaca orders with status |

---

## 🖥️ Web API v3

| Endpoint | Description |
|---|---|
| `GET /` | Institutional web cockpit |
| `WS /ws` | **Live WebSocket** decision stream (agent events pushed in real time) |
| `GET /api/health` | Liveness probe |
| `GET /api/account` | Live account + Greeks + clock |
| `GET /api/performance` | Real SQLite analytics + equity curve |
| `GET /api/journal` | Persistent trade journal |
| `GET /api/news` | Live regime + headlines |
| `GET /api/market-data` | Stress index, watchlist quotes, market clock |
| `GET /api/orders` | Order blotter |
| `GET /api/positions/marks` | Open options marked-to-market with management state |
| `POST /api/close-position` | Manual one-click close (journals P&L) |
| `POST /api/run-cycle` | Trigger an autonomous cycle |
| `POST /api/toggle-auto` | 24/7 background loop |

---

## ✅ Verified Test Suite — 16 Tests

```bash
python -m unittest tests.test_suite -v
```

Covers: Black-Scholes Greeks, live Alpaca connectivity, quant screening, sentiment structure, risk veto gates, autonomous tail-hedge execution, OCC symbol parsing, SQLite journal lifecycle (open→close→P&L→duplicate guard), performance analytics (win rate, profit factor, drawdown), market clock + real stress index, RSS news ingestion, position marks, notifier graceful degradation, all 11 Web API routes, all 11 MCP tools, and the Orchestrator v2 pipeline contract.

---

## 🏆 Hackathon Deliverables

- 📄 **One-Page Technical Write-Up:** [`docs/one_page_writeup.md`](docs/one_page_writeup.md)
- 📊 **Master Pitch Deck (PPTX):** [`docs/AEGIS_Pitch_Deck_ApexArbitrage.pptx`](docs/AEGIS_Pitch_Deck_ApexArbitrage.pptx)
- 🎥 **Video Pitch Script + Production Mechanism:** [`docs/video_pitch_script.md`](docs/video_pitch_script.md)
- 📱 **Social Media Posts:** [`docs/social_media_posts.md`](docs/social_media_posts.md)
- 🥇 **Winning Strategy Guide:** [`docs/HACKATHON_WINNING_GUIDE.md`](docs/HACKATHON_WINNING_GUIDE.md)
- 🔊 **AI Voice Briefing:** generated live on the dashboard (ElevenLabs)

---

## 🧠 Why AEGIS Is Different

| Capability | Typical Bot | AEGIS v3 |
|---|---|---|
| Position lifecycle | Opens only | **Opens → manages → closes** (TP/SL/roll/expiry) |
| News | LLM memory (stale) | **Live RSS ingestion**, grounded prompts |
| Market awareness | None | **Market clock guard** — never trades into closed sessions |
| Risk index | Hardcoded | **Real SPY ATM-IV VIX-proxy** with realized-vol fallback |
| Tail hedge | Logged only | **Actually executes** protective puts with cooldown |
| Persistence | Lost on restart | **SQLite journal** — trades, equity curve, cycles, hedges |
| Performance stats | Hardcoded | **Measured** — Sharpe, drawdown, profit factor from the journal |
| Duplicate protection | None | **Position-state guards** prevent stacking |
| Delivery | REST polling | **WebSocket** real-time decision stream |
| Access | Dashboard only | Dashboard + **CLI (10 cmds)** + **MCP (11 tools)** |

---

## 👥 Team Aegis

- **Zunurain Tahir** — Quant Agent & Risk/Governance Logic
- **Abdullah Khalid** — Alpaca MCP/CLI Integration & Sentiment Agent
- **Loraine** — Reporting Dashboard, Analytics & Demo Video

---

## ⚠️ Disclaimer

AEGIS trades on **Alpaca paper accounts only**. Options involve substantial risk; this project is an educational hackathon entry, not financial advice.
