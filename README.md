# 🛡️ AEGIS — Autonomous, Risk-Governed Options Income Desk
### Alpaca AI Trading Agents Hackathon — LabLab.ai × Alpaca ($6,300 Prize Pool)

[![Alpaca Trading API](https://img.shields.io/badge/Alpaca-Trading%20API%20%26%20MCP-blue?style=for-the-badge&logo=alpaca)](https://alpaca.markets)
[![FastMCP Protocol](https://img.shields.io/badge/FastMCP-Model%20Context%20Protocol-emerald?style=for-the-badge)](https://github.com/jlowin/fastmcp)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-yellow?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Modern%20Web%20Cockpit-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)

---

## 📌 Executive Overview
**AEGIS** is an institutional-grade, multi-agent autonomous options trading platform built on Alpaca's Trading API, FastMCP server, and CLI tools. 

Instead of taking high-variance directional bets that expose portfolios to market swings, Aegis systematically harvests option premium through a defined-risk Covered Call / Cash-Secured Put **"Wheel" strategy** across liquid blue chips and ETFs (`SPY`, `QQQ`, `AAPL`, `MSFT`, `NVDA`, `AMZN`, `TSLA`). 

The entire execution lifecycle is guarded by an **independent AI Risk & Governance Agent equipped with absolute veto power and autonomous tail-risk protective put hedging**.

---

## 🏛️ Triad Multi-Agent Architecture

```
                                 ┌─────────────────────────┐
                                 │   Alpaca Market Data    │
                                 └────────────┬────────────┘
                                              │
                                              ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│   Live News & Catalysts │ ───► │       Quant Agent       │ (IV Rank, DTE 14-45, Delta 0.15-0.30)
└────────────┬────────────┘      └────────────┬────────────┘
             │                                │ Proposes Wheel Tickets
             ▼                                ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│     Sentiment Agent     │ ───► │      Orchestrator       │
│  (Multi-LLM Consensus)  │      └────────────┬────────────┘
└─────────────────────────┘                   │
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Risk Governance Agent  │◄─── Portfolio Greeks Engine
                                 │ (VETO & TAIL HEDGING)   │
                                 └────────────┬────────────┘
                                              │ Verified / Vetoed
                                              ▼
                                 ┌─────────────────────────┐
                                 │ Alpaca FastMCP / Engine │ ───► Alpaca Paper Brokerage
                                 └─────────────────────────┘
```

1. **Quant Agent:** Screens live option chains via Alpaca, computes Black-Scholes Greeks ($\Delta, \Gamma, \Theta, \mathcal{V}$), selects 0.15–0.30 delta puts and covered calls, and optimizes annualized yield.
2. **Sentiment & Catalyst Agent:** Ensembles multi-LLM consensus (Groq Llama-3.3-70B, Gemini 1.5 Flash, DeepSeek, Mistral) to evaluate news and verify earnings blackout dates.
3. **Risk & Governance Agent (Sovereign Authority):** Computes portfolio Greeks in real time, enforces hard position limits ($\le 10\%$), ticker concentration ($\le 20\%$), drawdown circuit breakers, and **autonomously purchases SPY/QQQ protective puts** when market stress spikes.

---

## 🚀 Getting Started

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/MZunurainTahir/aegis.git
cd aegis
python -m venv venv
venv\Scripts\activate   # On Windows
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
```env
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_PAPER=true
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
DEEPSEEK_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here
```

### 3. Launch the Institutional Light-Themed Web Cockpit
```bash
python -m uvicorn src.web.app:app --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000`** in your browser.

---

## 💻 CLI Commands & Headless Execution

Run the scriptable Aegis CLI for cron jobs, CI/CD, or automated trading:
```bash
# Check live account balance, portfolio Greeks, and open positions
python src/cli.py --status

# Screen watchlist options chains for optimal Wheel opportunities
python src/cli.py --screen

# Execute one full 3-agent autonomous trading cycle
python src/cli.py --run-cycle

# Run independent tail-risk stress test and trigger protective put hedge
python src/cli.py --hedge
```

---

## 🔌 FastMCP Server for AI Assistants

Aegis includes a high-performance FastMCP server allowing Cursor, Claude, or autonomous LLM loops to query tools:
```bash
python src/mcp/fastmcp_server.py
```
**Exposed Tools:**
- `aegis_get_account_and_greeks`
- `aegis_screen_wheel_opportunities`
- `aegis_evaluate_risk`
- `aegis_run_trading_cycle`
- `aegis_trigger_autonomous_hedge`

---

## 🏆 Hackathon Deliverables

- 📄 **One-Page Technical Write-Up:** [`docs/one_page_writeup.md`](docs/one_page_writeup.md)
- 📊 **10-Slide Investor & Judge Pitch Deck:** [`docs/presentation_slides.md`](docs/presentation_slides.md)
- 🎥 **3-Minute Video Pitch Script:** [`docs/video_pitch_script.md`](docs/video_pitch_script.md)
- 📱 **5 Social Media Posts (X & LinkedIn):** [`docs/social_media_posts.md`](docs/social_media_posts.md)
- 🥇 **Master Winning Strategy Guide:** [`docs/HACKATHON_WINNING_GUIDE.md`](docs/HACKATHON_WINNING_GUIDE.md)

---

## 👥 Team Aegis
- **Zunurain Tahir** — Quant Agent & Risk/Governance Logic
- **Abdullah Khalid** — Alpaca MCP/CLI Integration & Sentiment Agent
- **Loraine** — Reporting Dashboard, Backtesting, Demo Video & Socials
