# Project AEGIS v3.1: Autonomous, Risk-Governed Options Income Desk
**Hackathon Event:** Alpaca AI Trading Agents Hackathon — lablab.ai × Alpaca
**Track:** Options Alpha / Income & Portfolio Overlay Agents
**Team Name:** ApexArbitrage
**Team Members:** Muhammad Zun U Rain Tahir, Anne Loraine A. Pardillo, Muhammad Abdullah Khalid
**Dedicated Paper Account ID:** `a6f90060-9a9d-4ab6-949b-3238a0a40615`
**Starting Balance:** $100,000.00 USD
**Live Cockpit:** https://web-production-5ded7.up.railway.app
**Repository:** https://github.com/MZunurainTahir/aegis

---

## 1. Executive Summary & Problem Formulation

Most algorithmic trading submissions rely on a high-variance paradigm: a single LLM analyzes indicators and news, then places directional, unhedged bets — and then *walks away*. Two failure modes follow: (1) one adverse macro headline erases a week of gains, and (2) nobody is home to close, roll, or take profit on open positions, so paper P&L never converts to realized P&L.

**AEGIS introduces structural alpha through governed premium harvesting — and it runs the complete lifecycle.** AEGIS systematically harvests option decay via the Covered Call / Cash-Secured Put "Wheel" across liquid blue chips (SPY, QQQ, AAPL, MSFT, NVDA, AMZN), then **manages every open position autonomously**: 50% take-profit rules, 200% stop-losses, ITM rolls at ≤5 DTE, and expiry-day sweeps — all journaled to a persistent SQLite trade ledger with real, measured performance analytics.

---

## 2. AI Logic — Five Agents & the Autonomous Cycle

**1. News Agent** — Ingests live Google News RSS headlines (zero API keys), classifies the market regime (RISK_ON / NEUTRAL / RISK_OFF / CRISIS) once per cycle via an LLM call grounded in actual headlines (never model memory), and detects earnings proximity for blackout gating.

**2. Quant Agent** — Screens live option chains; computes Black-Scholes Greeks (Δ, Γ, Θ, V) and IV-rank-adjusted annualized yield; enforces duplicate-position guards (never stacks a second short option on the same ticker) and cash-reserve-aware position sizing.

**3. Sentiment Agent** — Runs a **multi-LLM ensemble** (Groq Llama-3.3-70B → Cerebras → Gemini Flash → DeepSeek → Mistral → OpenRouter failover chain) on *live headlines per ticker*, producing conviction scores (1–100) with earnings-blackout hard overrides and majority-veto on disagreement.

**4. Risk Governance Agent** — Sovereign veto authority (see §3).

**5. Portfolio Manager** — Runs *first* in every cycle: marks all open short options to market via live quotes and executes take-profit (50%), stop-loss (200%), roll (ITM ≤5 DTE), and expiry sweeps, booking realized P&L to the journal.

**Orchestrator v2** coordinates all five in a fixed manage-first pipeline — market-hours check → account audit → position management → regime classification → screening → sentiment gate → risk governance → execution → tail-hedge check → journaling — with a threading cycle-lock (no overlapping runs), a market-hours guard (management-only audits when closed), SQLite journaling of every trade/cycle/equity snapshot, and Telegram alerts.

---

## 3. Risk Gates — Sovereign Governance & Tail Hedging

The Risk Governance Agent holds **absolute veto power**: no other agent — and no human shortcut — can bypass its deterministic gates.

| Gate | Limit |
|:---|:---|
| Max equity per trade | ≤ 10% |
| Max exposure per ticker | ≤ 20% |
| Minimum cash reserve | ≥ 5% |
| Portfolio delta bounds | [−100Δ, +250Δ] |
| Stress-index hedge trigger | > 25 |
| Hedge cooldown | 20 hours |

- **Real stress measurement** — a VIX-proxy computed from live SPY ATM ~30-DTE implied volatility (realized-vol fallback), never a hardcoded constant.
- **Executed tail hedges** — when stress > 25, the agent selects a real ~14-DTE SPY put ~4% OTM from the live chain and buys it at the ask for a reliable fill; every hedge (contract, strike, cost, reason, order id) is journaled.
- **Earnings blackout** — sentiment optimism is overridden to veto when a quarterly report is imminent; premium is never sold into a binary event.

---

## 4. Alpaca Infrastructure Implementation

AEGIS is built **natively on Alpaca's Trading API** via the `alpaca-py` SDK, running on a dedicated paper account:

- **Option chain snapshots** — the Quant Agent pulls live chains per ticker to compute strikes, deltas, and IV-rank-adjusted yields for screening.
- **Real-time quote snapshots** — every open short option is marked to market with live quotes each cycle; account endpoints supply equity, buying power, cash, and day P&L.
- **Market Clock API** — drives the market-hours guard: closed sessions run management-only audits; approved orders are deferred, never thrown.
- **Order lifecycle** — real limit orders that pay the ask for reliable fills; the blotter tracks submission → fill; **failures return `success: false` and are journaled honestly — no fake confirmations, ever**.
- **Position tracking** — the Portfolio Manager reconciles open positions against Alpaca and executes buy-to-close on take-profit/stop-loss/roll/expiry.
- **Full P&L loop on Alpaca paper** — proposals screened from live Alpaca data, executed through the risk gate, closed by rule, and measured in the journal.

---

## 5. The Operator Experience (v3.1)

- **Professional web cockpit** — WebSocket live decision stream, metric cards, proposal/position tables, terminal feed, deterministic risk-gate panel; zero-build vanilla-JS frontend with a 40+ symbol SVG icon system.
- **Command palette & shortcuts** — `Ctrl+K` (13 commands); single keys: `R` cycle · `A` auto-trade · `H` hedge · `B` briefing · `T` dark theme · `E` CSV export.
- **Market telemetry** — live ticker-tape marquee, market open/close countdown, regime tiles, Greeks monitor (delta band, theta income, stress gauge vs. the 25 threshold, cash deployed).
- **Attribution & analytics** — realized-P&L heatmap per ticker, per-strategy performance bars, journal search/filters, one-click CSV export, equity chart with zoom timeframes.
- **Awareness layer** — notification center with unread badge (fills, vetoes, hedges), WebAudio sound alerts, dark theme.
- **Executive voice briefings** — ElevenLabs Turbo v2.5 narrates live equity, net delta, theta yield, realized P&L, and win rate; pre-loaded at login, instant in-memory playback, background regeneration, Web Speech fallback.

---

## 6. Technology Stack

| Layer | Technology |
|:---|:---|
| Trading & Market Data | `alpaca-py` — option chains, snapshots, Greeks, market clock, orders |
| Persistence | SQLite (WAL) journal — trades, equity snapshots, cycles, hedges + analytics engine (Sharpe, drawdown, profit factor, win rate) |
| AI Inference | Six-provider LLM ensemble with failover, rate-limit cooldowns, consensus mode |
| Live Data | Google News RSS (stdlib XML), SPY ATM-IV VIX-proxy stress index |
| Web Cockpit | FastAPI (non-blocking threadpool handlers) + WebSocket; command palette, dark theme, Greeks monitor |
| Protocol / CLI | FastMCP server (11 tools for Claude/Cursor) · 10 CLI commands with JSON output |
| Alerts & Voice | Telegram notifier · ElevenLabs TTS |
| Deployment | Railway (live) — `Dockerfile` + `Procfile` included |

---

## 7. Engineering Integrity & Verification

- **Every stat is measured** — win rate, Sharpe, drawdown, profit factor computed from the SQLite journal, not hardcoded.
- **Auditable evidence** — the trade journal (`data/aegis_journal.db`) is committed to the repo: every fill, veto, hedge, and equity snapshot is timestamped and inspectable.
- **16-test verification suite** — Black-Scholes accuracy, live Alpaca connectivity, veto gates, tail-hedge execution, OCC parsing, journal lifecycle, analytics math, RSS ingestion, route/tool registration, pipeline contract — all passing.

**Verify live:** sign in at the cockpit → `Run AI Cycle` → watch the WebSocket stream screen, veto, and execute → play the voice briefing → export the journal CSV.

**Judging alignment:** P&L is banked through rule-based exits and verifiable in the committed journal; creativity shows in the five-agent sovereign-risk architecture, six-LLM consensus, executed tail hedges, and the voice-commanded operator experience.
