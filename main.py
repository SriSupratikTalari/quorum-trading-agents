import json
import argparse
from datetime import date
from pathlib import Path

from orchestrator import run_ticker
from tools.trading_tools import get_clock,get_account
from tools.portfolio_tools import get_latest_price
from config import UNIVERSE,BENCHMARK

DATA=Path(__file__).resolve().parent/"data"

def save(state:dict):
    # Full record of every decision and its reasoning
    day=DATA/"runs"/state["date"]
    day.mkdir(parents=True,exist_ok=True)
    (day/f"{state['ticker']}.json").write_text(json.dumps(state,indent=2,default=str))
    # Latest outputs, so Bull/Bear/PM can be tested alone without rerunning research
    for name in ("research","bull","bear"):
        (DATA/f"sample_{name}_{state['ticker']}.json").write_text(json.dumps(state[name],indent=2,default=str))

def log_performance():
    """One row per day: portfolio value vs SPY price. This is how we track 'beat SPY'."""
    path=DATA/"performance.csv"
    new=not path.exists()
    equity=get_account()["equity"]
    spy=get_latest_price(BENCHMARK)["price"]
    with open(path,"a") as f:
        if new:
            f.write("date,equity,spy_price\n")
        f.write(f"{date.today().isoformat()},{equity},{spy}\n")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--tickers",nargs="*",default=UNIVERSE,help="default: the full universe")
    p.add_argument("--force",action="store_true",help="run even if the market is closed (no trades placed)")
    args=p.parse_args()

    if not get_clock()["is_open"] and not args.force:
        print("Market is closed. Use --force to run anyway (no trades will be placed).")
        return

    # One ticker at a time, so each one sees the cash and positions left by the last trade
    for ticker in args.tickers:
        print(f"--- {ticker} ---")
        try:
            state=run_ticker(ticker)
            save(state)
            d,r,e=state["decision"],state["risk"],state["execution"]
            print(f"PM: {d.get('action')} (conf {d.get('confidence')}) | "
                  f"Risk: {r.get('status')} | Exec: {e.get('status')} {e.get('reason','')}")
        except Exception as ex:
            print(f"{ticker} failed: {ex}")

    log_performance()

if __name__=="__main__":
    main()