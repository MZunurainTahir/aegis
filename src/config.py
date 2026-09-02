import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# Load .env file automatically
load_dotenv(find_dotenv())

BASE_DIR = Path(__file__).resolve().parent.parent

# Alpaca API Credentials
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets" if ALPACA_PAPER else "https://api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets"

# AI Inference Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")

# Voice / Audio Keys
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
SPEECHMATICS_API_KEY = os.getenv("SPEECHMATICS_API_KEY", "")

# Supabase — User Auth & Profile Storage
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Target Trading Universe for Options Wheel Strategy
DEFAULT_WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "PLTR", "SOFI", "AMD", "INTC"]

# Risk & Governance Limits (Institutional Rules)
RISK_RULES = {
    "MAX_CAPITAL_PER_POSITION_PCT": 0.35,   # Max 35% of equity per position (Standard Reg-T Cash-Secured Put allocation)
    "MAX_EXPOSURE_PER_TICKER_PCT": 0.40,    # Max 40% of equity per ticker
    "MAX_PORTFOLIO_DELTA": 250.0,           # Target neutral-to-mildly bullish
    "MIN_PORTFOLIO_DELTA": -100.0,
    "DRAWDOWN_CIRCUIT_BREAKER_PCT": 0.05,  # Pause selling new premium if drawdown > 5%
    "TARGET_DTE_MIN": 7,                    # 7 to 45 Days to Expiration
    "TARGET_DTE_MAX": 45,
    "PUT_TARGET_DELTA_MIN": 0.15,          # Delta range for Cash-Secured Puts
    "PUT_TARGET_DELTA_MAX": 0.30,
    "CALL_TARGET_DELTA_MIN": 0.20,         # Delta range for Covered Calls
    "CALL_TARGET_DELTA_MAX": 0.35,
    "PROFIT_TAKE_PCT": 0.50,               # Close short option at 50% max profit
    "STOP_LOSS_PCT": 2.00,                 # Stop loss at 200% loss on premium
    "STRESS_VIX_HEDGE_THRESHOLD": 25.0     # Trigger automatic tail hedge when stress spikes
}

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
DECISION_LOG_PATH = LOGS_DIR / "decision_audit_trail.json"
AUDIO_OUTPUT_DIR = BASE_DIR / "static" / "audio"
AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
