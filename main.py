"""
main.py
WHEN and WHICH stocks run, and what gets recorded. Daily order:
  1. Rules first: stops + rebalance
  2. Research (3 stocks at once) -> decisions (one at a time)
  3. Bench, once, if cash was freed
  4. Save, log performance, alert if many agents failed (e.g. OpenAI out of credit)
"""
import json
import argparse
from datetime import date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import state
from alerts import alert
from orchestrator import research_ticker, decide_ticker
from rules import check_positions
from bench import run_bench
from tools.trading_tools import get_clock, get_account
from tools.portfolio_tools import get_latest_price
from config import BENCHMARK, RESEARCH_WORKERS, AGENT_FAIL_ALERT, TRADING_ENABLED

DATA = Path(__file__).resolve().parent / "data"
RESEARCH_AGENTS = ("fundamentals", "technical", "news", "macro")


def save(st: dict):
    # Full record of every decision and its reasoning
    day = DATA / "runs" / st["date"]
    day.mkdir(parents=True, exist_ok=True)
    (day / f"{st['ticker']}.json").write_text(json.dumps(st, indent=2, default=str))
    # Latest outputs, so Bull/Bear/PM can be tested alone without rerunning research
    for name in ("research", "bull", "bear"):
        if name in st:
            (DATA / f"sample_{name}_{st['ticker']}.json").write_text(json.dumps(st[name], indent=2, default=str))


def log_performance():
    """One row per day: portfolio value vs SPY price. Re-runs replace today's row."""
    path = DATA / "performance.csv"
    today = date.today().isoformat()
    rows = path.read_text().splitlines()[1:] if path.exists() else []
    rows = [r for r in rows if r and not r.startswith(today)]   # drop today's old row
    equity = get_account()["equity"]
    spy = get_latest_price(BENCHMARK)["price"]
    rows.append(f"{today},{equity},{spy}")
    path.write_text("date,equity,spy_price\n" + "\n".join(rows) + "\n")


def count_failures(st: dict) -> tuple:
    research = st.get("research") or {}
    failed = sum(1 for a in RESEARCH_AGENTS if "error" in (research.get(a) or {"error": 1}))
    return failed, len(RESEARCH_AGENTS)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", nargs="*", default=None, help="default: the active list in data/state.json")
    p.add_argument("--force", action="store_true", help="run even if the market is closed (no trades placed)")
    p.add_argument("--no-bench", action="store_true")
    args = p.parse_args()
    tickers = args.tickers or state.load()["active"]

    if not get_clock()["is_open"] and not args.force:
        print("Market is closed. Use --force to run anyway (no trades will be placed).")
        return
    if not TRADING_ENABLED:
        alert("🛑 TRADING_ENABLED is off: running research only, no orders will be sent.")

    # 1. Rules first (stops, rebalance)
    try:
        for r in check_positions():
            print(f"RULE {r['rule']}: {r['ticker']} -> {r.get('status')}")
    except Exception as e:
        alert(f"⚠️ rule check failed: {e}")

    # 2. Research 3 stocks at a time (safe: no money involved)
    with ThreadPoolExecutor(max_workers=RESEARCH_WORKERS) as pool:
        futures = {t: pool.submit(research_ticker, t) for t in tickers}

    # Decide one at a time, so each sees the cash left by the last trade
    failed = total = 0
    for ticker in tickers:
        print(f"--- {ticker} ---", flush=True)
        try:
            st = decide_ticker(futures[ticker].result())
            save(st)
            f, n = count_failures(st)
            failed, total = failed + f, total + n
            d, r, e = st["decision"], st["risk"], st["execution"]
            print(f"PM: {d.get('action')} (conf {d.get('confidence')}) | "
                  f"Risk: {r.get('status')} | Exec: {e.get('status')} {e.get('reason', '')}", flush=True)
        except Exception as ex:
            failed, total = failed + len(RESEARCH_AGENTS), total + len(RESEARCH_AGENTS)
            print(f"{ticker} failed: {ex}", flush=True)

    # Loud alert if the agents are failing (e.g. OpenAI out of credit). Otherwise it looks like a "hold" day.
    if total and failed / total >= AGENT_FAIL_ALERT:
        alert(f"🚨 {failed}/{total} research agents failed today. Check OpenAI credit/keys and the run logs.")

    # 3. Bench, once a day, only if cash was freed
    if not args.no_bench:
        try:
            run_bench(save_fn=save)
        except Exception as e:
            alert(f"⚠️ bench failed: {e}")

    # 4. Scoreboard
    try:
        log_performance()
    except Exception as e:
        alert(f"⚠️ performance log failed: {e}")


if __name__ == "__main__":
    main()