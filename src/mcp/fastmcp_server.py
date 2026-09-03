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
from src.agents.portfolio_manager import portfolio_manager
from src.agents.news_agent import news_agent
from src.persistence.database import journal

logger = logging.getLogger("Aegis.MCP")

# Initialize FastMCP Server for Aegis
mcp = FastMCP("Aegis-Autonomous-Options-Engine")


@mcp.tool()
def aegis_get_account_and_greeks() -> str:
    """
    Retrieves the live Alpaca account status, buying power, equity, aggregated portfolio Greeks (Delta, Theta, Vega, Gamma), market session state, and the live SPY-IV stress index.
    """
    acc = alpaca_service.get_account_summary()
    greeks = alpaca_service.calculate_portfolio_greeks()
    positions = alpaca_service.get_positions()
    clock = alpaca_service.get_market_clock()
    stress = alpaca_service.get_market_stress_index()
    return json.dumps({
        "account": acc,
        "portfolio_greeks": greeks,
        "open_positions": positions,
        "market_clock": clock,
        "stress_index": stress,
    }, indent=2)


@mcp.tool()
def aegis_screen_wheel_opportunities(watchlist: str = "SPY,QQQ,AAPL,MSFT,NVDA,AMZN") -> str:
    """
    Screens options chains across the designated watchlist to find optimal Cash-Secured Put and Covered Call candidates. Includes IV rank, annualized yield, and duplicate-position guards (never stacks a second short option on the same ticker).
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
    Evaluates a proposed option trade ticket through the News-grounded Sentiment Agent (multi-LLM ensemble) and the Risk Agent's deterministic governance limits.
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
    Triggers a full autonomous multi-agent trading cycle: position management (profit-take/stop-loss/roll) -> live news regime -> screening -> sentiment scoring -> risk audit -> execution & audit trail -> tail hedge check -> journal persistence.
    """
    results = orchestrator.run_full_cycle(force_execute=True)
    return json.dumps(results, indent=2, default=str)


@mcp.tool()
def aegis_trigger_autonomous_hedge(stress_index: float = None) -> str:
    """
    Evaluates the REAL market stress index (SPY ATM implied volatility VIX-proxy) and portfolio delta to independently deploy a protective SPY/QQQ put tail hedge with real order execution. Pass a stress_index to override, or omit to use live market data.
    """
    res = risk_agent.check_and_trigger_tail_hedge(market_stress_index=stress_index)
    return json.dumps(res, indent=2, default=str)


@mcp.tool()
def aegis_get_performance_analytics() -> str:
    """
    Returns REAL performance analytics computed from the persistent SQLite trade journal: realized P&L, win rate, profit factor, Sharpe ratio, max drawdown, equity curve, per-strategy breakdown, and cycle history.
    """
    analytics = journal.get_performance_analytics(starting_equity=100000.0)
    equity_curve = journal.get_equity_curve(limit=100)
    cycles = journal.get_cycle_history(limit=10)
    return json.dumps({
        "performance": analytics,
        "equity_curve": equity_curve,
        "recent_cycles": cycles,
    }, indent=2, default=str)


@mcp.tool()
def aegis_get_trade_journal(limit: int = 20) -> str:
    """
    Returns the persistent trade journal: every order lifecycle event with entry/exit premiums, realized P&L attribution, conviction scores, and risk verdicts.
    """
    trades = journal.get_trade_journal(limit=limit)
    hedges = journal.get_hedge_history(limit=10)
    return json.dumps({
        "trades": trades,
        "hedge_history": hedges,
    }, indent=2, default=str)


@mcp.tool()
def aegis_manage_positions() -> str:
    """
    Runs the Portfolio Manager sweep: executes take-profit (50%), stop-loss (200%), ITM rolls, and expiry sweeps across all open short option positions — realizing P&L and journaling every action.
    """
    result = portfolio_manager.manage_open_positions()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def aegis_get_market_regime() -> str:
    """
    Classifies the live market regime (RISK_ON / NEUTRAL / RISK_OFF / CRISIS) from REAL Google News RSS headlines via the multi-LLM ensemble, including key risks and premium-selling guidance.
    """
    regime = news_agent.classify_market_regime()
    return json.dumps(regime, indent=2, default=str)


@mcp.tool()
def aegis_get_news(ticker: str = "market") -> str:
    """
    Fetches live news headlines from Google News RSS for a ticker (or the overall market if ticker='market').
    """
    if ticker.lower() in ("market", "overall", "index"):
        headlines = news_agent.fetch_market_news(limit=10)
    else:
        headlines = news_agent.fetch_ticker_news(ticker, limit=10)
    return json.dumps({
        "query": ticker,
        "headlines": headlines,
    }, indent=2)


@mcp.tool()
def aegis_get_order_blotter(limit: int = 20) -> str:
    """
    Returns the live order blotter from Alpaca — recent orders with fill status, prices, and timestamps for full order lifecycle tracking.
    """
    orders = alpaca_service.get_recent_orders(limit=limit)
    return json.dumps({
        "count": len(orders),
        "orders": orders,
    }, indent=2, default=str)


def start_mcp_server():
    """Runs the FastMCP server."""
    logger.info("Starting Aegis FastMCP Server v3.0 for Claude/Cursor/Agent integration...")
    mcp.run()

if __name__ == "__main__":
    start_mcp_server()
