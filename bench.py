"""
bench.py
The bench: a waiting list of extra stocks. When selling frees up cash, the bench is checked ONCE that day:
  1. Order: stocks that were sold and finished their cooldown first (oldest sale first),
     then the rest by a quick free score (90-day strength vs SPY + analyst upside).
  2. Free filter (no LLM): skip if below the 200-day average, RSI too high, earnings soon,
     in cooldown, already owned, or its sector is full.
  3. Full analysis ONE stock at a time; stop at the first buy or after BENCH_MAX_FULL_CHECKS.
A bench stock that gets bought moves to the active list (done in execution_agent).
"""
import state
from alerts import alert
from config import (RULES, BENCH_MAX_FULL_CHECKS, BENCH_MAX_RSI, BENCH_MIN_FREE_CASH,
                    MIN_CASH_WEIGHT, MAX_SECTOR_WEIGHT)
from rules import earnings_blocks_buy
from tools.trading_tools import get_account, get_all_positions
from tools.technical_tools import get_quick_check
from tools.valuation_tools import get_valuation, days_to_earnings


def cash_freed(account: dict) -> bool:
    return account["equity"] and account["cash"] / account["equity"] > MIN_CASH_WEIGHT + BENCH_MIN_FREE_CASH


def passes_free_filter(ticker: str, held: set, sector_weights: dict, s: dict):
    """Returns (passed, reason, quick_score). No LLM."""
    from agents.risk_agent import _sector
    if ticker in held:
        return False, "already owned", None
    if state.cooldown_until(ticker, s):
        return False, "in cooldown", None
    try:
        q = get_quick_check(ticker)
    except Exception as e:
        return False, f"no price data: {e}", None
    if not q["above_sma_200"]:
        return False, "below 200-day average", None
    if q["rsi_14"] > BENCH_MAX_RSI:
        return False, f"overheated (RSI {q['rsi_14']})", None
    if earnings_blocks_buy(days_to_earnings(ticker)):
        return False, "earnings within 2 days", None
    sector = _sector(ticker)
    if sector and sector_weights.get(sector, 0) >= MAX_SECTOR_WEIGHT - 0.02:
        return False, f"{sector} is full", None
    try:
        upside = get_valuation(ticker).get("upside_to_target") or 0
    except Exception:
        upside = 0
    return True, "ok", round(q["outperformance"] + 0.5 * upside, 4)


def ordered_candidates(s: dict, held: set, sector_weights: dict) -> list:
    sold, bench = s["sold"], s["bench"]
    returning, fresh = [], []
    for t in bench:
        ok, why, score = passes_free_filter(t, held, sector_weights, s)
        if not ok:
            print(f"  bench skip {t}: {why}", flush=True)
            continue
        (returning if t in sold else fresh).append((t, score))
    returning.sort(key=lambda x: sold[x[0]])        # oldest sale first
    fresh.sort(key=lambda x: x[1], reverse=True)    # best quick score first
    return [t for t, _ in returning + fresh]


def run_bench(save_fn=None, force: bool = False) -> list:
    """Run once per day, only if cash was freed. save_fn(state) saves each analysis (main.save)."""
    from orchestrator import research_ticker, decide_ticker
    from agents.risk_agent import _sector

    cfg = RULES["bench"]
    if not cfg["enabled"]:
        return []
    s = state.load()
    if s["bench_last_run"] == state.today() and not force:
        return []
    account = get_account()
    if not cash_freed(account) and not force:
        return []
    with state.edit() as st:
        st["bench_last_run"] = state.today()

    positions = get_all_positions()
    held = {p["ticker"] for p in positions}
    sector_weights = {}
    for p in positions:
        sec = _sector(p["ticker"])
        if sec:
            sector_weights[sec] = sector_weights.get(sec, 0) + p["market_value"] / account["equity"]

    candidates = ordered_candidates(s, held, sector_weights)
    alert(f"🪑 Bench: cash {account['cash'] / account['equity']:.1%}. Candidates in order: {candidates[:5]}")

    results = []
    for t in candidates[:BENCH_MAX_FULL_CHECKS]:
        st = decide_ticker(research_ticker(t), rule="bench", practice=cfg.get("practice", True))
        if save_fn:
            save_fn(st)
        e = st["execution"]
        results.append({"ticker": t, "action": st["decision"].get("action"), "status": e.get("status")})
        print(f"  bench {t}: PM {st['decision'].get('action')} | Risk {st['risk'].get('status')} | Exec {e.get('status')}", flush=True)
        if e.get("side") == "buy" and e.get("status") in ("filled", "partially_filled", "accepted", "new", "practice"):
            alert(f"🪑 Bench pick: {t} ({e.get('status')})")
            break
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run_bench(force=True), indent=2))