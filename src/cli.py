import argparse
import json
import sys
import time
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
from src.agents.portfolio_manager import portfolio_manager
from src.agents.news_agent import news_agent
from src.persistence.database import journal

def print_banner():
    print("=" * 70)
    print("      AEGIS v3.0: AUTONOMOUS RISK-GOVERNED OPTIONS INCOME DESK")
    print("      Alpaca AI Trading Agents Hackathon — LabLab.ai x Alpaca")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Aegis Autonomous Options Trading CLI v3.0")
    parser.add_argument("--run-cycle", action="store_true", help="Execute one complete autonomous multi-agent trading cycle (manage positions -> news -> screen -> sentiment -> risk -> execute -> hedge -> journal)")
    parser.add_argument("--status", action="store_true", help="Print live account balance, portfolio Greeks, market session, stress index, and active positions")
    parser.add_argument("--screen", action="store_true", help="Run Quant Agent to screen options chains for Wheel opportunities")
    parser.add_argument("--hedge", action="store_true", help="Check REAL market stress and trigger protective tail hedge if needed")
    parser.add_argument("--manage", action="store_true", help="Run Portfolio Manager: take-profit, stop-loss, roll, and expiry sweeps on open positions")
    parser.add_argument("--performance", action="store_true", help="Print REAL performance analytics from the SQLite trade journal")
    parser.add_argument("--journal", action="store_true", help="Print the persistent trade journal (last 25 trades)")
    parser.add_argument("--news", action="store_true", help="Fetch live market headlines and the current AI regime classification")
    parser.add_argument("--regime", action="store_true", help="Classify live market regime from real news (RISK_ON/NEUTRAL/RISK_OFF/CRISIS)")
    parser.add_argument("--loop", type=int, metavar="MINUTES", help="Run continuous autonomous cycles every N minutes (e.g. --loop 15)")
    parser.add_argument("--json", action="store_true", help="Output results in raw JSON format")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        print_banner()
        parser.print_help()
        sys.exit(0)

    if args.status:
        account = alpaca_service.get_account_summary()
        greeks = alpaca_service.calculate_portfolio_greeks()
        clock = alpaca_service.get_market_clock()
        stress = alpaca_service.get_market_stress_index()
        positions = alpaca_service.get_positions()

        if args.json:
            print(json.dumps({
                "account": account, "greeks": greeks, "clock": clock,
                "stress_index": stress, "positions": positions,
            }, indent=2, default=str))
        else:
            print_banner()
            print(f"[*] Account:           {account['account_id']}")
            print(f"    Equity:           ${account['equity']:,.2f}")
            print(f"    Cash:             ${account['cash']:,.2f}")
            print(f"    Buying Power:      ${account['buying_power']:,.2f}")
            print(f"    Day P&L:           ${account['day_pnl']:+,.2f} ({account['day_pnl_pct']:+.2f}%)")
            print(f"    Net Delta:         {greeks['net_delta']}")
            print(f"    Daily Theta:       ${greeks['daily_theta_income']}")
            print(f"    Market Open:       {clock.get('is_open')}")
            print(f"    Stress Index:      {stress} (hedge threshold: 25.0)")
            print(f"    Open Positions:    {len(positions)}")

    elif args.screen:
        proposals = quant_agent.screen_opportunities()
        if args.json:
            print(json.dumps(proposals, indent=2))
        else:
            print_banner()
            print(f"[*] Quant Agent screened {len(proposals)} Wheel opportunities:\n")
            for i, p in enumerate(proposals[:10], 1):
                print(f"  {i}. {p['ticker']:5s} {p['strategy']:18s} ${p['strike']:>8.2f} strike | {p['dte']}d DTE | "
                      f"delta {p['delta']:+.2f} | IV rank {p.get('iv_rank', '—')} | ${p['total_credit']:>7.2f} credit | {p['annualized_yield']:.1f}% ann.")

    elif args.hedge:
        res = risk_agent.check_and_trigger_tail_hedge()
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            print_banner()
            print(f"[*] Market Stress Index (REAL SPY IV proxy):  {res['stress_index']}")
            print(f"    Hedge Threshold:                            {res['threshold']}")
            print(f"    Hedge Triggered:                            {res['hedge_triggered']}")
            if res['hedge_triggered']:
                print(f"    Action Taken:                               {json.dumps(res['hedge_action'], indent=2, default=str)}")
            else:
                print("    Status: All risk limits normal. Portfolio delta balanced.")

    elif args.manage:
        res = portfolio_manager.manage_open_positions()
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            print_banner()
            print(f"[*] Portfolio Manager sweep complete:")
            print(f"    Open short options:  {res.get('open_short_options', 0)}")
            print(f"    Actions executed:    {res.get('managed', 0)}")
            print(f"    Realized P&L:        ${res.get('realized_pnl', 0):+,.2f}")
            for a in res.get("actions", []):
                print(f"      - [{a['action']}] {a['contract_symbol']} -> ${a['realized_pnl']:+.2f}")

    elif args.performance:
        perf = journal.get_performance_analytics(starting_equity=100000.0)
        if args.json:
            print(json.dumps(perf, indent=2))
        else:
            print_banner()
            print("[*] LIVE PERFORMANCE ANALYTICS (SQLite trade journal):\n")
            print(f"    Current Equity:        ${perf['current_equity']:,.2f}")
            print(f"    Total Return:          {perf['total_return_pct']:+.2f}%")
            print(f"    Realized P&L:          ${perf['total_realized_pnl']:+,.2f}")
            print(f"    Closed Trades:         {perf['closed_trades']} ({perf['winning_trades']}W / {perf['losing_trades']}L)")
            print(f"    Win Rate:              {perf['win_rate_pct']}%")
            print(f"    Profit Factor:         {perf['profit_factor']}")
            print(f"    Sharpe Ratio:          {perf['sharpe_ratio']}")
            print(f"    Max Drawdown:          {perf['max_drawdown_pct']}%")
            print(f"    Open Positions:        {perf['open_positions']}")
            print(f"    Total Cycles Run:      {perf['total_cycles']}")
            print(f"    Tail Hedges Deployed:  {perf['total_hedges']}")
            print(f"    Risk Vetoes:           {perf['total_vetoes']}")

    elif args.journal:
        trades = journal.get_trade_journal(limit=25)
        if args.json:
            print(json.dumps(trades, indent=2, default=str))
        else:
            print_banner()
            print(f"[*] Trade Journal (last {len(trades)} entries):\n")
            for t in trades:
                pnl = t['realized_pnl'] or 0
                pnl_s = f"${pnl:+.2f}" if t['status'] != 'OPEN' else "—"
                print(f"  {t['id']:>4} | {t['ticker']:5s} | {(t['strategy'] or ''):18s} | {(t['side'] or ''):14s} | "
                      f"@${(t['premium'] or 0):>7.2f} | {t['status']:8s} | {pnl_s}")

    elif args.news or args.regime:
        regime = news_agent.classify_market_regime()
        if args.json:
            print(json.dumps(regime, indent=2, default=str))
        else:
            print_banner()
            print(f"[*] Live Market Regime: {regime['regime']} (confidence {regime['confidence']}%)")
            print(f"    Summary: {regime['summary']}")
            print(f"    Volatility Expectation: {regime['volatility_expectation']}")
            print(f"    Premium Selling Favorable: {regime['premium_selling_favorable']}")
            print(f"\n    Top Live Headlines (Google News RSS):")
            for h in regime.get("headlines", [])[:8]:
                print(f"      - {h['title']}  ({h.get('source', '')})")

    elif args.loop:
        interval = max(1, args.loop) * 60
        print_banner()
        print(f"[*] Entering CONTINUOUS AUTONOMOUS MODE: cycle every {args.loop} minute(s). Ctrl+C to stop.\n")
        cycle_no = 0
        try:
            while True:
                cycle_no += 1
                print(f"\n===== CYCLE {cycle_no} @ {datetime.now(timezone.utc).isoformat()} =====")
                try:
                    cycle = orchestrator.run_full_cycle(force_execute=True)
                    print(f"[+] Executed: {len(cycle['executed_trades'])} | Vetoed: {len(cycle['vetoed_trades'])} | "
                          f"Managed: {cycle['management']['managed']} | Realized: ${cycle['management']['realized_pnl']:+.2f}")
                except Exception as e:
                    print(f"[!] Cycle error: {e}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[*] Continuous mode stopped by operator.")

    elif args.run_cycle:
        if not args.json:
            print_banner()
            print("[*] Running Aegis Multi-Agent Autonomous Cycle...\n")

        cycle = orchestrator.run_full_cycle(force_execute=True)
        if args.json:
            print(json.dumps(cycle, indent=2, default=str))
        else:
            print("[+] Cycle Execution Summary:")
            print(f"    Timestamp:         {cycle['timestamp']}")
            print(f"    Cycle Mode:        {cycle.get('cycle_mode', 'N/A')} (market open: {cycle.get('market_open')})")
            print(f"    Proposals Screened:{cycle['proposals_count']}")
            print(f"    Executed Trades:   {len(cycle['executed_trades'])}")
            print(f"    Vetoed Trades:     {len(cycle['vetoed_trades'])}")
            mgmt = cycle.get('management', {})
            print(f"    Managed Positions: {mgmt.get('managed', 0)} (realized ${mgmt.get('realized_pnl', 0):+.2f})")
            perf = cycle.get('performance', {})
            print(f"    Lifetime Realized: ${perf.get('total_realized_pnl', 0):+.2f} | Win rate: {perf.get('win_rate_pct', 0)}%")
            print(f"    Briefing Text:     {cycle['briefing_text']}")
            if cycle.get("audio_briefing_url"):
                print(f"    Audio Briefing:    {cycle['audio_briefing_url']}")

if __name__ == "__main__":
    main()
