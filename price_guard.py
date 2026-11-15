"""
price_guard.py
Runs 24/7 on the server (replaces watcher.py). Every PRICE_GUARD_MINUTES:
  1. Market open: stop + rebalance rules (plain Python, free).
  2. For each stock you own: new headlines since the last check (free).
     Keyword filter (free) -> only then the News agent (LLM), max once per stock per hour.
  3. Critical news (2 signals):
       - market closed     -> alert only (the 7am daily run reviews it)
       - gapped down 5%+   -> full pipeline, the PM decides (the market already reacted)
       - in profit         -> wait 30 min; if the price is still lower, sell HALF (news_sell rule)
       - at a loss         -> full pipeline, the PM decides
     News score dropped 3+ points (not critical) -> full pipeline review.
"""
import time
from datetime import datetime, timedelta, timezone

import state
from alerts import alert
from config import PRICE_GUARD_MINUTES, NEWS_CONFIRM_MINUTES, NEWS_DROP_TRIGGER, RULES
from rules import check_positions, headline_hits, is_critical_news, gapped_down, rule_trade
from tools.trading_tools import get_clock, get_all_positions
from tools.technical_tools import get_snapshot
from tools.news_tools import get_headlines_since


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def full_review(ticker: str, why: str):
    """Run the whole pipeline for one stock (max MAX_ALERT_RUNS_PER_DAY per day)."""
    from orchestrator import run_ticker
    from main import save
    with state.edit() as s:
        if not state.can_alert_run(s, ticker):
            alert(f"{ticker}: skipped review (daily alert-run limit) | {why}")
            return
        state.add_alert_run(s, ticker)
    st = run_ticker(ticker)
    st["trigger"] = why
    save(st)
    alert(f"🔎 {ticker} review ({why}): PM {st['decision'].get('action')} | "
          f"Risk {st['risk'].get('status')} | Exec {st['execution'].get('status')}")


def handle_pending(positions: dict):
    """30-minute confirmation for news sell-half."""
    s = state.load()
    for ticker, p in list(s["pending_news_sells"].items()):
        waited = datetime.now() - datetime.fromisoformat(p["alert_time"])
        if ticker not in positions:
            done, msg = True, None
        elif waited < timedelta(minutes=NEWS_CONFIRM_MINUTES):
            continue
        else:
            price = get_snapshot(ticker)["price"]
            done = True
            if price and price <= p["alert_price"]:
                qty = int(positions[ticker]["qty"])
                rule_trade(ticker, "sell", max(qty // 2, 1), "news_sell",
                           f"critical news confirmed: {p['alert_price']:.2f} -> {price:.2f} after {NEWS_CONFIRM_MINUTES} min | {p['reason']}")
                msg = None
            else:
                msg = f"✅ {ticker}: price recovered ({p['alert_price']:.2f} -> {price}), news sell cancelled"
        if done:
            with state.edit() as st:
                st["pending_news_sells"].pop(ticker, None)
            if msg:
                alert(msg)


def check_news(ticker: str, pos: dict, market_open: bool):
    from agents import news_agent

    s = state.load()
    since = s["last_headline_check"].get(ticker) or utc_iso(datetime.now() - timedelta(hours=2))
    now = utc_iso(datetime.now())
    headlines = get_headlines_since(ticker, since)
    with state.edit() as st:
        st["last_headline_check"][ticker] = now
        hits = [h for h in headlines if headline_hits(h["headline"])]
        if not hits or not state.can_run_news(st, ticker):
            return
        st["last_news_run"][ticker] = datetime.now().isoformat(timespec="seconds")
        old = st["last_news_score"].get(ticker)

    report = news_agent.run(ticker)                       # the only LLM call in this loop
    new = report.get("score")
    with state.edit() as st:
        if new is not None:
            st["last_news_score"][ticker] = new

    critical, why = is_critical_news(report)
    big_drop = old is not None and new is not None and old - new >= NEWS_DROP_TRIGGER
    if not (critical or big_drop):
        return

    alert(f"⚠️ {ticker}: {'CRITICAL news' if critical else f'news score {old} → {new}'} ({why})\n"
          f"{(report.get('severity_reason') or report.get('summary') or '')[:400]}")
    if not market_open:
        alert(f"{ticker}: market closed, the next daily run will review it")
        return
    if not critical:
        full_review(ticker, f"news score {old} → {new}")
        return

    snap = get_snapshot(ticker)
    in_profit = (pos.get("unrealized_pl_pct") or 0) > 0
    if gapped_down(snap["open"], snap["prev_close"]):
        full_review(ticker, "critical news, but the stock already gapped down: PM decides")
    elif in_profit and RULES["news_sell"]["enabled"]:
        with state.edit() as st:
            st["pending_news_sells"][ticker] = {"alert_price": snap["price"],
                                                "alert_time": datetime.now().isoformat(timespec="seconds"),
                                                "reason": why}
        alert(f"⏳ {ticker}: in profit, will sell half if still below {snap['price']} in {NEWS_CONFIRM_MINUTES} min")
    else:
        full_review(ticker, "critical news on a losing position: PM decides")


def check_once():
    market_open = get_clock()["is_open"]
    if market_open:
        for r in check_positions():
            print(f"RULE {r['rule']}: {r['ticker']} -> {r.get('status')}", flush=True)
    positions = {p["ticker"]: p for p in get_all_positions()}
    if market_open:
        handle_pending(positions)
    for ticker, pos in positions.items():
        try:
            check_news(ticker, pos, market_open)
        except Exception as e:
            print(f"{ticker} news check failed: {e}", flush=True)


def main():
    alert("🛡️ Price guard started")
    while True:
        try:
            check_once()
        except Exception as e:
            alert(f"price guard error: {e}")
        time.sleep(PRICE_GUARD_MINUTES * 60)


if __name__ == "__main__":
    main()