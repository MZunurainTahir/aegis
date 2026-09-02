import json
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastmcp import FastMCP
from src.alpaca_client.alpaca_service import alpaca_service
from src.agents.quant_agent import quant_agent
from src.agents.sentiment_agent import sentiment_agent
from src.agents.risk_agent import risk_agent
from src.agents.orchestrator import orchestrator

logger = logging.getLogger("Aegis.MCP")

# Initialize FastMCP Server for Aegis
mcp = FastMCP("Aegis-Autonomous-Options-Engine")

@mcp.tool()
def aegis_get_account_and_greeks() -> str:
    """
    Retrieves the live Alpaca account status, buying power, equity, and aggregated portfolio Greeks (Delta, Theta, Vega, Gamma).
    """
    acc = alpaca_service.get_account_summary()
    greeks = alpaca_service.calculate_portfolio_greeks()
    positions = alpaca_service.get_positions()
    return json.dumps({
        "account": acc,
        "portfolio_greeks": greeks,
        "open_positions": positions
    }, indent=2)

@mcp.tool()
def aegis_screen_wheel_opportunities(watchlist: str = "SPY,QQQ,AAPL,MSFT,NVDA,AMZN") -> str:
    """
    Screens options chains across the designated watchlist to find optimal Cash-Secured Put and Covered Call candidates.
    """
    tickers = [t.strip() for t in watchlist.split(",") if t.strip()]
    quant = quant_agent
    quant.watchlist = tickers
    proposals = quant.screen_opportunities()
    return json.dumps({
        "screened_tickers": tickers,
        "count": len(proposals),
        "proposals": proposals
    }, indent=2)

@mcp.tool()
def aegis_evaluate_risk(ticker: str, strategy: str, strike: float, spot_price: float, dte: int, collateral: float) -> str:
    """
    Evaluates a proposed option trade ticket through Sentiment Agent news scoring and Risk Agent deterministic governance limits.
    """
    candidate = {
        "ticker": ticker,
        "strategy": strategy,
        "strike": strike,
        "spot_price": spot_price,
        "dte": dte,
        "collateral_required": collateral
    }
    sent_res = sentiment_agent.evaluate_proposal(candidate)
    approved, verdict, meta = risk_agent.audit_trade_proposal(candidate, sent_res)
    return json.dumps({
        "trade_ticket": candidate,
        "sentiment_score": sent_res,
        "approved": approved,
        "verdict": verdict,
        "risk_metadata": meta
    }, indent=2)

@mcp.tool()
def aegis_run_trading_cycle() -> str:
    """
    Triggers a full autonomous 3-agent trading cycle: screening -> sentiment scoring -> risk audit -> execution & audit trail.
    """
    results = orchestrator.run_full_cycle(force_execute=True)
    return json.dumps(results, indent=2)

@mcp.tool()
def aegis_trigger_autonomous_hedge(stress_index: float = 26.0) -> str:
    """
    Evaluates market stress index and portfolio delta to independently deploy a protective SPY/QQQ put tail hedge.
    """
    res = risk_agent.check_and_trigger_tail_hedge(market_stress_index=stress_index)
    return json.dumps(res, indent=2)

def start_mcp_server():
    """Runs the FastMCP server."""
    logger.info("Starting Aegis FastMCP Server for Claude/Cursor/Agent integration...")
    mcp.run()

if __name__ == "__main__":
    start_mcp_server()
