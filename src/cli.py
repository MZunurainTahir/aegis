import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from datetime import datetime, timezone
from src.alpaca_client.alpaca_service import alpaca_service
from src.agents.quant_agent import quant_agent
from src.agents.sentiment_agent import sentiment_agent
from src.agents.risk_agent import risk_agent
from src.agents.orchestrator import orchestrator

def print_banner():
    print("=" * 70)
    print("      AEGIS: AUTONOMOUS RISK-GOVERNED OPTIONS INCOME DESK")
    print("      Alpaca AI Trading Agents Hackathon — LabLab.ai x Alpaca")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Aegis Autonomous Options Trading CLI")
    parser.add_argument("--run-cycle", action="store_true", help="Execute one complete autonomous multi-agent trading cycle")
    parser.add_argument("--status", action="store_true", help="Print live account balance, portfolio Greeks, and active positions")
    parser.add_argument("--screen", action="store_true", help="Run Quant Agent to screen options chains for Wheel opportunities")
    parser.add_argument("--hedge", action="store_true", help="Check market stress and trigger protective tail hedge if needed")
    parser.add_argument("--json", action="store_true", help="Output results in raw JSON format")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        print_banner()
        parser.print_help()
        sys.exit(0)

    if args.status:
        if not args.json:
            print_banner()
            print("[*] Fetching Alpaca Account Status & Portfolio Greeks...\n")
        
        acc = alpaca_service.get_account_summary()
        greeks = alpaca_service.calculate_portfolio_greeks()
        positions = alpaca_service.get_positions()

        data = {
            "account": acc,
            "portfolio_greeks": greeks,
            "positions_count": len(positions),
            "positions": positions
        }

        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"Account ID:     {acc['account_id']}")
            print(f"Status:         {acc['status']}")
            print(f"Equity:         ${acc['equity']:,.2f}")
            print(f"Cash:           ${acc['cash']:,.2f}")
            print(f"Buying Power:   ${acc['buying_power']:,.2f}")
            print(f"Day P&L:        ${acc['day_pnl']:,.2f} ({acc['day_pnl_pct']}%)")
            print("-" * 50)
            print(f"Portfolio Delta: {greeks['net_delta']} (Neutral-to-Bullish band)")
            print(f"Daily Theta:     ${greeks['daily_theta_income']} (Income rate/day)")
            print(f"Portfolio Vega:  {greeks['net_vega']}")
            print("-" * 50)
            print(f"Active Positions: {len(positions)}")
            for p in positions:
                print(f"  • {p['symbol']} | Qty: {p['qty']} | Mkt Val: ${p['market_value']:,.2f} | Unrealized: ${p['unrealized_pl']:,.2f} ({p['unrealized_plpc']}%)")

    elif args.screen:
        if not args.json:
            print_banner()
            print("[*] Quant Agent screening watchlist for Wheel Opportunities...\n")
        
        props = quant_agent.screen_opportunities()
        if args.json:
            print(json.dumps(props, indent=2))
        else:
            print(f"Found {len(props)} high-conviction candidate trades:\n")
            for i, p in enumerate(props, 1):
                print(f"[{i}] {p['strategy']} on {p['ticker']}")
                print(f"    Contract: {p['contract_symbol']} | Strike: ${p['strike']} | DTE: {p['dte']}d")
                print(f"    Delta: {p['delta']} | Est Premium: ${p['estimated_premium']} (Total Credit: ${p['total_credit']})")
                print(f"    Annualized Yield: {p['annualized_yield']}% | Collateral Req: ${p['collateral_required']:,.2f}")
                print(f"    Thesis: {p['agent_thesis']}\n")

    elif args.hedge:
        if not args.json:
            print_banner()
            print("[*] Risk Agent Stress Testing & Tail-Hedge Verification...\n")
        
        res = risk_agent.check_and_trigger_tail_hedge()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Market Stress Index:  {res['stress_index']}")
            print(f"Hedge Threshold:      {res['threshold']}")
            print(f"Hedge Triggered:      {res['hedge_triggered']}")
            if res['hedge_triggered']:
                print(f"Action Taken:         {res['hedge_action']}")
            else:
                print("Status: All risk limits normal. Portfolio delta balanced.")

    elif args.run_cycle:
        if not args.json:
            print_banner()
            print("[*] Running Aegis Multi-Agent Autonomous Cycle...\n")
        
        cycle = orchestrator.run_full_cycle(force_execute=True)
        if args.json:
            print(json.dumps(cycle, indent=2))
        else:
            print("[+] Cycle Execution Summary:")
            print(f"    Timestamp:         {cycle['timestamp']}")
            print(f"    Proposals Screened:{cycle['proposals_count']}")
            print(f"    Executed Trades:   {len(cycle['executed_trades'])}")
            print(f"    Vetoed Trades:     {len(cycle['vetoed_trades'])}")
            print(f"    Briefing Text:     {cycle['briefing_text']}")
            if cycle.get("audio_briefing_url"):
                print(f"    Audio Briefing:    {cycle['audio_briefing_url']}")

if __name__ == "__main__":
    main()
