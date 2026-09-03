# AEGIS v3.1 — Autonomous, Risk-Governed Options Income Desk

### Alpaca AI Trading Agents Hackathon — LabLab.ai × Alpaca

[![Alpaca Trading API](https://img.shields.io/badge/Alpaca-Trading%20API%20%26%20MCP-blue?style=for-the-badge&logo=alpaca)](https://alpaca.markets)
[![FastMCP Protocol](https://img.shields.io/badge/FastMCP-11%20Tools-emerald?style=for-the-badge)](https://github.com/jlowin/fastmcp)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-yellow?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-WebSocket%20Cockpit-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-Persistent%20Journal-lightgrey?style=for-the-badge&logo=sqlite)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)

---

## Table of Contents

1. [Executive Overview](#-executive-overview)
2. [Complete Feature Set](#-complete-feature-set)
3. [System Architecture](#-five-agent-architecture)
4. [The Autonomous Cycle](#-the-autonomous-cycle-orchestrator-v2)
5. [Risk Governance & Tail Hedging](#-risk-governance--tail-hedging)
6. [Persistence & Performance Analytics](#-persistence--performance-analytics)
7. [Web Cockpit v3.1](#-web-cockpit-v31)
8. [Voice Intelligence](#-voice-intelligence)
9. [Access Surfaces](#-access-surfaces)
10. [Getting Started](#-getting-started)
11. [Testing](#-verified-test-suite)
12. [Why AEGIS Is Different](#-why-aegis-is-different)
13. [Team](#-team-apexarbitrage)
14. [Disclaimer](#%EF%B8%8F-disclaimer)

---

## Executive Overview

**AEGIS** is an institutional-grade, **five-agent autonomous options trading platform** built on Alpaca's Trading API. It runs the complete Wheel-strategy lifecycle — **discover, sell premium, manage, hedge, and close** — with zero human intervention:

- **Sells defined-risk premium** — Cash-Secured Puts (0.15–0.30Δ) and Covered Calls (0.20–0.35Δ), 7–45 DTE — on liquid blue chips and ETFs (`SPY`, `QQQ`, `AAPL`, `MSFT`, `NVDA`, `AMZN`, …)
- **Manages every open position autonomously** — 50% take-profit, 200% stop-loss, ITM rolls, and expiry-day sweeps, booking realized P&L to a persistent journal
- **Refuses to trade blind** — ingests live news via RSS, classifies the market regime (RISK_ON / NEUTRAL / RISK_OFF / CRISIS), and enforces earnings blackouts
- **Guards itself with a sovereign Risk Agent** — absolute veto power over every proposal, plus **real tail-hedge execution** when its SPY ATM-IV stress index spikes above 25
- **Journals everything to SQLite** — every order, veto, hedge, equity snapshot, and cycle — and computes real performance analytics (Sharpe, drawdown, profit factor, win rate)
- **Reports to humans like a desk, not a log file** — executive AI voice briefings (ElevenLabs), a professional web cockpit with command palette and dark mode, Telegram pushes, and CSV exports

Every number on the dashboard is **real, measured, and auditable**. Nothing is simulated or hardcoded.

---

## Complete Feature Set

### Autonomous Trading Engine

| Feature | Detail |
|---|---|
| Wheel-strategy lifecycle | CSP (0.15–0.30Δ) → assignment/roll → Covered Calls (0.20–0.35Δ), 7–45 DTE |
| Five-agent pipeline | News → Quant → Sentiment → Risk Governance → Portfolio Manager, orchestrated by a cycle engine |
| Manage-first execution | Portfolio Manager runs **before** any new trade is proposed — realized P&L first, new exposure second |
| Cycle lock | Threading mutex rejects overlapping runs (`SKIPPED_OVERLAPPING`) |
| Market-hours guard | Alpaca clock gate — management-only audits when the session is closed |
| 24/7 auto-loop | Background async loop (configurable interval, min 60s) or manual `Run AI Cycle` |
| Per-cycle trade cap | Max 3 new positions per cycle to control exposure ramps |
| Manual override | Trade ticket routed through the same risk gates as autonomous orders |

### Position Management (Portfolio Manager)

| Rule | Trigger | Action |
|---|---|---|
| Take-profit | Mark ≤ 50% of entry premium | Buy-to-close, journal realized P&L |
| Stop-loss | Mark ≥ 200% of entry premium | Exit before losses compound |
| Roll | ITM and ≤ 5 DTE | Close and re-strike — the wheel keeps spinning |
| Expiry sweep | DTE = 0 | Final-day close or expire-worthless cleanup |
| Mark-to-market | Every cycle | Live quotes per open contract, management state per row (HOLD / TP / SL / ROLL / EXPIRY) |

### Market Intelligence

| Feature | Detail |
|---|---|
| Live news ingestion | Google News RSS (stdlib XML parsing) — market-wide and per-ticker feeds, zero API keys |
| Regime classification | RISK_ON / NEUTRAL / RISK_OFF / CRISIS with confidence, volatility expectation, and key risks — computed from live headlines, never model memory |
| Earnings blackout | Regex + LLM detection of imminent reports → hard veto (never sell premium into binary events) |
| Sentiment ensemble | Six LLM providers with automatic failover and rate-limit cooldowns; conviction scoring 1–100; majority veto on disagreement |
| Real stress index | SPY ATM ~30-DTE implied volatility (VIX-proxy) computed from the live chain, with realized-vol fallback |

### Risk Governance

| Gate | Limit |
|---|---|
| Max equity per trade | ≤ 10% |
| Max exposure per ticker | ≤ 20% |
| Minimum cash reserve | ≥ 5% |
| Portfolio delta bounds | [−100Δ, +250Δ] |
| Tail hedge trigger | Stress index > 25 → execute ~14-DTE SPY protective put ~4% OTM at the ask |
| Hedge cooldown | 20 hours — prevents hedge stacking |
| Veto authority | Sovereign — no agent or human path bypasses the gates |

### Web Cockpit (v3.1)

| Feature | Detail |
|---|---|
| Live decision stream | WebSocket pushes every agent event in real time — cycle lock status, vetoes, fills |
| Metric cards | Equity, day P&L, net delta, daily theta income, stress index, buying power — live from Alpaca |
| Agent status bar | Five agent pills with per-cycle state |
| Screened proposals | Quant Agent table with IV-rank, delta, premium, annualized yield |
| Position management | Open options with entry premium, live mark, P&L %, Greeks, management state + one-click **Close Now** |
| Performance analytics | Equity curve chart with All / 50 / 20 timeframe zoom, Sharpe, drawdown, profit factor, win rate |
| P&L attribution | Ticker heatmap (realized P&L intensity) + per-strategy performance bars |
| Greeks monitor | Net-delta marker on the allowed band, theta income fill, stress gauge vs. the 25 hedge threshold, cash-deployed ratio |
| Trade journal | Persistent blotter with full-text search, OPEN/CLOSED status filter, and timestamped CSV export |
| Market monitor | Regime pill, session state, live watchlist ticker-tape marquee, market countdown clock |
| Command palette | `Ctrl+K` — 13 fuzzy-searchable commands |
| Keyboard shortcuts | `R` cycle · `A` auto · `H` hedge · `B` briefing · `T` theme · `E` export · `F` fullscreen · `?` cheat-sheet · `Esc` close |
| Notification center | Unread badge; trade fills, risk vetoes, hedge events — timestamped |
| Sound alerts | Distinct WebAudio tones for trades, vetoes, and hedges (toggleable) |
| Dark theme | One-click institutional night mode, persisted across sessions |
| SVG icon system | 40+ inline symbols — crisp at any DPI, zero icon-font dependency |
| Auth | Register / sign-in with password strength meter and visibility toggles; Supabase-ready with local fallback |

### Voice Intelligence (ElevenLabs)

One click narrates an executive briefing — live equity, net delta, daily theta yield, realized P&L, win rate — via ElevenLabs Turbo v2.5:

- Audio is **pre-loaded at login** and starts **instantly** from an in-memory cache
- Regeneration happens in the **background** — playback is never blocked
- Volume slider, dedicated regenerate button, and status pill (READY / LOADING / PLAYING / GENERATING)
- Fallback chain: cached MP3 → regenerate → Web Speech synthesis

---

## Five-Agent Architecture

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
│ delta targeting,  │    │  ITM rolls, expiry sweep,│  realized P&L journaling
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

## The Autonomous Cycle (Orchestrator v2)

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

## Risk Governance & Tail Hedging

The Risk Governance Agent is deliberately **sovereign**: no other agent — and no human shortcut — can bypass its gates.

- **Deterministic limits** — ≤10% equity per trade, ≤20% per ticker, ≥5% cash reserve, portfolio delta within [−100Δ, +250Δ]
- **Real stress measurement** — a VIX-proxy computed from live SPY ATM ~30-DTE implied volatility (realized-vol fallback), never a hardcoded constant
- **Executed tail hedges** — when stress > 25, the agent finds a real ~14-DTE SPY put ~4% OTM from the live chain and buys it at the ask for a reliable fill
- **Cooldown discipline** — a 20-hour window after each hedge prevents over-hedging
- **Full auditability** — every hedge (contract, strike, cost, reason, order id) is journaled

---

## Persistence & Performance Analytics

A SQLite journal in WAL mode records the desk's entire life — `trades`, `equity_snapshots`, `cycle_history`, `hedges` — so the system **remembers its book across restarts**, and every claim is verifiable against an append-only ledger.

The analytics engine computes from real history only:

- Realized P&L (total and per strategy)
- Win rate, profit factor, average win/loss
- Sharpe ratio (from equity-curve returns, annualized)
- Maximum drawdown from the running peak
- Live equity curve rendered to the dashboard chart

---

## Web Cockpit v3.1

A zero-build, vanilla-JS institutional cockpit served by FastAPI — with non-blocking threadpool handlers so the UI stays responsive under live market load.

- **Real-time** — WebSocket decision stream; agent events, vetoes, and fills the moment they happen
- **Complete desk** — proposals, positions, marks, performance, attribution, journal, news, terminal, risk gates
- **Operator-grade UX** — command palette, keyboard shortcuts, notification center, sound alerts, dark theme, ticker tape, countdown clock, Greeks monitor
- **Data portability** — one-click CSV export of the full trade journal

---

## Voice Intelligence

The briefing text is composed from **live account state** — equity, net delta, theta yield, realized P&L, win rate — synthesized through ElevenLabs and served as a cached MP3. Playback is engineered to never stall: pre-loaded at login, in-memory replay, background regeneration, and a Web Speech fallback.

---

## Access Surfaces

### Web API (FastAPI)

| Endpoint | Description |
|---|---|
| `GET /` | Institutional web cockpit |
| `WS /ws` | **Live WebSocket** decision stream |
| `GET /api/health` | Liveness probe |
| `POST /api/register` | Account registration (Supabase-ready, local fallback) |
| `POST /api/login` | Sign-in + Alpaca credential binding |
| `GET /api/account` | Live account + Greeks + clock + stress |
| `GET /api/screen` | Quant Agent screening results |
| `GET /api/logs` | In-memory decision audit stream |
| `POST /api/run-cycle` | Trigger an autonomous cycle |
| `POST /api/toggle-auto` | 24/7 background loop |
| `POST /api/trigger-hedge` | Manual tail-hedge evaluation |
| `POST /api/execute-trade` | Manual trade through the risk gate |
| `GET /api/performance` | Real SQLite analytics + equity curve |
| `GET /api/journal` | Persistent trade journal |
| `GET /api/news` | Live regime + headlines |
| `GET /api/market-data` | Stress index, watchlist quotes, market clock |
| `GET /api/orders` | Order blotter |
| `GET /api/positions/marks` | Open options marked-to-market |
| `POST /api/close-position` | One-click close (journals P&L) |
| `GET /api/audio-briefing` | Generate live voice briefing (ElevenLabs) |
| `GET /api/backtest-stats` | Live-forward statistics from the journal |

### CLI — 10 Headless Commands

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

### FastMCP Server — 11 Tools for AI Assistants

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

### Telegram Alerts

Every execution, veto, hedge, and cycle summary is pushed to your phone in real time.

---

## Getting Started

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

Open **http://127.0.0.1:8000** — register, sign in, and the desk is live.

### 4. Docker (optional)

```bash
docker build -t aegis .
docker run --env-file .env -p 8000:8000 aegis
```

---

## Verified Test Suite

```bash
python -m unittest tests.test_suite -v
```

Covers: Black-Scholes Greeks, live Alpaca connectivity, quant screening, sentiment structure, risk veto gates, autonomous tail-hedge execution, OCC symbol parsing, SQLite journal lifecycle (open→close→P&L→duplicate guard), performance analytics (win rate, profit factor, drawdown), market clock + real stress index, RSS news ingestion, position marks, notifier graceful degradation, all Web API routes, all 11 MCP tools, and the Orchestrator v2 pipeline contract.

---

## Why AEGIS Is Different

| Capability | Typical Bot | AEGIS v3.1 |
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
| Human interface | Raw logs | **Voice briefings + command palette + dark cockpit + CSV** |
| Access | Dashboard only | Dashboard + **CLI (10 cmds)** + **MCP (11 tools)** + **Telegram** |

---

## Team ApexArbitrage

- **Zunurain Tahir** — Quant Agent & Risk/Governance Logic
- **Abdullah Khalid** — Alpaca MCP/CLI Integration & Sentiment Agent
- **Loraine Pardillo** — Reporting Dashboard, Analytics & Demo Video

---

## ⚠️ Disclaimer

AEGIS trades on **Alpaca paper accounts only**. Options involve substantial risk; this project is an educational hackathon entry, not financial advice.
