"""
rules.py
Quorum's automatic rules (plain Python, no LLM):
  1. Stop: 10% max loss, breakeven once up 10%, 20% trailing from peak. Wider for jumpy stocks.
     Sells only after STOP_CONFIRM_CHECKS checks in a row below the stop.
  2. Rebalance: trim any stock above 12% back to 10%.
  3. Market mode: strong market -> 25% trailing stop and 15% rebalance.
  4. News sell-half: helpers to decide if news is critical (2 signals) and the gap rule.
  5. Daily cap, practice mode, cooldown and earnings checks.

The pure functions at the top have no API calls, so tests/test_rules.py can check the math.
"""
import math
from datetime import date, timedelta

import state
from alerts import alert
from config import (RULES, MAX_RULE_TRADES_PER_DAY, MAX_LOSS_PCT, BREAKEVEN_AT, TRAIL_PCT, TRAIL_PCT_STRONG,
                    STOP_VOL_REF, MAX_LOSS_CAP, TRAIL_CAP, STOP_CONFIRM_CHECKS, REBALANCE_ABOVE,
                    REBALANCE_ABOVE_STRONG, REBALANCE_TO, NEWS_CRITICAL_SCORE, NEWS_MAJOR_OUTLETS,
                    NEWS_KEYWORDS, MAJOR_OUTLETS, NEWS_GAP_PCT, EARNINGS_BLOCK_DAYS)

MIN_TRADE_VALUE = 100.0

# =====================================================================
# PURE FUNCTIONS (tested)
# =====================================================================


def stop_price(entry: float, peak: float, vol, strong_market: bool = False) -> float:
    """Price at which the stop sells. The highest of: max-loss stop, trailing stop, breakeven lock."""
    scale = max(1.0, (vol or STOP_VOL_REF) / STOP_VOL_REF)        # jumpy stocks get wider stops
    max_loss = min(MAX_LOSS_PCT * scale, MAX_LOSS_CAP)
    trail = min((TRAIL_PCT_STRONG if strong_market else TRAIL_PCT) * scale, TRAIL_CAP)
    stop = max(entry * (1 - max_loss), peak * (1 - trail))
    if peak / entry - 1 >= BREAKEVEN_AT - 1e-9:                   # up 10% -> never sell below the buy price
        stop = max(stop, entry)
    return round(stop, 2)


def next_stop_count(count: int, price: float, stop: float) -> int:
    """Checks in a row the price has been below the stop. Resets once it's back above."""
    return count + 1 if price < stop else 0


def stop_triggered(count: int) -> bool:
    return count >= STOP_CONFIRM_CHECKS


def rebalance_shares(value: float, equity: float, price: float, strong_market: bool = False) -> int:
    """Shares to sell to bring a position from above the limit back down to REBALANCE_TO."""
    above = REBALANCE_ABOVE_STRONG if strong_market else REBALANCE_ABOVE
    if not equity or not price or value / equity <= above:
        return 0
    excess = value - REBALANCE_TO * equity
    return math.ceil(excess / price) if excess >= MIN_TRADE_VALUE else 0


def headline_hits(headline: str) -> bool:
    h = (headline or "").lower()
    return any(k in h for k in NEWS_KEYWORDS)


def major_outlet_count(articles: list) -> int:
    """How many different major outlets ran a red-flag headline."""
    outlets = set()
    for a in articles or []:
        pub = (a.get("publisher") or "").lower()
        if headline_hits(a.get("headline")):
            for m in MAJOR_OUTLETS:
                if m in pub:
                    outlets.add(m)
    return len(outlets)


def is_critical_news(report: dict, days: int = 7) -> tuple:
    """Needs 2 independent signals:
       1) LLM: score <= NEWS_CRITICAL_SCORE and severity == 'critical'
       2) Hard fact: a serious 8-K in the last `days` days, OR 2+ major outlets with red-flag headlines."""
    data = report.get("data") or {}
    llm = (report.get("score") or 10) <= NEWS_CRITICAL_SCORE and report.get("severity") == "critical"
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    serious_8k = any(f.get("serious") and f.get("filing_date", "") >= cutoff for f in data.get("filings_8k") or [])
    outlets = major_outlet_count(data.get("articles"))
    hard = serious_8k or outlets >= NEWS_MAJOR_OUTLETS
    why = f"score {report.get('score')}, severity {report.get('severity')}, serious 8-K {serious_8k}, major outlets {outlets}"
    return (llm and hard), why


def gapped_down(open_price, prev_close) -> bool:
    """Stock already opened 5%+ below yesterday's close: the market reacted first, so let the PM decide."""
    return bool(open_price and prev_close and open_price / prev_close - 1 <= -NEWS_GAP_PCT)


def earnings_blocks_buy(days_to_earnings) -> bool:
    return days_to_earnings is not None and 0 <= days_to_earnings <= EARNINGS_BLOCK_DAYS


# =====================================================================
# TRADING (uses APIs)
# =====================================================================

def rule_trade(ticker: str, side: str, shares: int, rule: str, reason: str) -> dict:
    """Place a rule-based trade, respecting the rule's switch, practice mode, and the daily cap."""
    from agents.execution_agent import execute   # imported here to keep this file light for tests

    cfg = RULES.get(rule, {"enabled": False})
    if not cfg["enabled"]:
        return {"status": "skipped", "reason": f"rule '{rule}' is off"}
    practice = cfg.get("practice", True)
    if not practice and state.rule_trades_today(state.load()) >= MAX_RULE_TRADES_PER_DAY:
        alert(f"⏸️ {rule}: daily cap of {MAX_RULE_TRADES_PER_DAY} rule trades reached, skipped {side} {shares} {ticker}")
        return {"status": "skipped", "reason": "daily rule-trade cap reached"}

    risk_like = {"ticker": ticker, "status": "approved", "final_order": {"side": side, "shares": shares}}
    res = execute(risk_like, rule=rule, reason=reason, practice=practice)
    tag = "🧪 PRACTICE" if practice else "⚙️ RULE"
    alert(f"{tag} {rule}: {side} {shares} {ticker} → {res.get('status')} | {reason}")
    return res


def check_positions() -> list:
    """Stop + rebalance for every position. Run by main.py and every 15 min by price_guard.py.
    Only acts while the market is open (peaks only count regular-hours prices)."""
    from tools.trading_tools import get_clock, get_account, get_all_positions
    from tools.technical_tools import get_volatility
    from tools.marcos_tools import get_market_mode

    if not get_clock()["is_open"]:
        return []
    account = get_account()
    positions = get_all_positions()
    strong = get_market_mode().get("strong", False)
    held = {p["ticker"] for p in positions}
    vols = {p["ticker"]: get_volatility(p["ticker"]) for p in positions}   # cached for the day

    to_sell = []   # decide inside the lock, trade after it's released
    with state.edit() as s:
        for t in [t for t in s["positions"] if t not in held]:
            s["positions"].pop(t)                                          # sold outside Quorum
        for p in positions:
            t, price, entry = p["ticker"], p["current_price"], p["avg_entry_price"]
            if not price or not entry:
                continue
            pos = s["positions"].setdefault(t, {"buy_date": state.today()})
            pos["entry"] = entry
            pos["peak"] = max(pos.get("peak") or entry, price)
            stop = stop_price(entry, pos["peak"], vols[t], strong)
            pos["stop"] = stop
            pos["below_stop_count"] = next_stop_count(pos.get("below_stop_count", 0), price, stop)
            if stop_triggered(pos["below_stop_count"]):
                pnl = price / entry - 1
                to_sell.append((t, "sell", int(p["qty"]), "stop",
                                f"price {price:.2f} below stop {stop:.2f} (entry {entry:.2f}, peak {pos['peak']:.2f}, P/L {pnl:+.1%})"))
                pos["below_stop_count"] = 0
                continue
            n = rebalance_shares(p["market_value"], account["equity"], price, strong)
            if n:
                to_sell.append((t, "sell", n, "rebalance",
                                f"weight {p['market_value'] / account['equity']:.1%} > limit, trim to 10%"))

    return [{"ticker": t, "rule": r, **rule_trade(t, side, n, r, why)} for t, side, n, r, why in to_sell]


def rule_context(ticker: str) -> dict:
    """What the PM needs to know about the automatic rules for this stock."""
    from tools.valuation_tools import days_to_earnings, get_next_earnings
    s = state.load()
    until = state.cooldown_until(ticker, s)
    dte = days_to_earnings(ticker)
    try:
        next_e = get_next_earnings(ticker)
    except Exception:
        next_e = None
    return {"in_cooldown": until is not None, "cooldown_until": until,
            "next_earnings": next_e, "days_to_earnings": dte,
            "earnings_block": earnings_blocks_buy(dte),
            "recent_rule_trades": state.recent_rule_trades(ticker, s=s),
            "position_rules": s["positions"].get(ticker.upper(), {})}


if __name__ == "__main__":
    import json
    print(json.dumps(check_positions(), indent=2, default=str))