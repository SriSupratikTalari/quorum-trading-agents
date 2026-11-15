"""
execution_agent.py
Plain Python (no LLM). Every trade in Quorum goes through execute().

Safety:
  - TRADING_ENABLED=false  -> nothing is sent to Alpaca
  - practice=True          -> logs what it WOULD do, sends nothing
  - market closed, open order, or selling more than owned -> skipped
Every attempt is logged to data/trades.csv with its reason, and state is updated
(buy date, cooldown, rule-trade count, active/bench lists).
"""
import csv
import time
from datetime import datetime
from pathlib import Path

import state
from config import TRADING_ENABLED
from tools.trading_tools import get_clock, get_open_orders, get_position, place_order, get_order

TRADES = Path(__file__).resolve().parents[1] / "data" / "trades.csv"
FIELDS = ["time", "ticker", "side", "shares", "rule", "status", "fill_price", "entry_price", "reason", "order_id"]


def log_trade(row: dict):
    TRADES.parent.mkdir(parents=True, exist_ok=True)
    new = not TRADES.exists()
    with open(TRADES, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({"time": datetime.now().isoformat(timespec="seconds"), **row})


def _update_state(ticker: str, side: str, shares: int, rule: str, reason: str, fill_price):
    """Called after a real fill. Never call this inside a state.edit() block."""
    remaining = float(get_position(ticker)["qty"] or 0) if side == "sell" else None
    with state.edit() as s:
        if side == "buy":
            pos = s["positions"].setdefault(ticker, {})
            pos.setdefault("buy_date", state.today())
            if fill_price:
                pos["peak"] = max(pos.get("peak") or 0, float(fill_price))
            state.move_to_active(s, ticker)
        else:
            if rule != "pm":
                state.set_cooldown(s, ticker)            # stop the PM from instantly rebuying
            if remaining == 0:
                state.move_to_bench(s, ticker)           # fully sold -> back of the bench
        if rule != "pm":
            state.add_rule_trade(s, {"date": state.today(), "ticker": ticker, "side": side,
                                     "shares": shares, "rule": rule, "reason": reason})


def execute(risk_output: dict, rule: str = "pm", reason: str = "", practice: bool = False) -> dict:
    ticker = risk_output["ticker"].upper()
    order = risk_output.get("final_order") or {}
    side, shares = order.get("side"), int(order.get("shares") or 0)
    result = {"agent": "execution", "ticker": ticker, "side": side, "shares": shares, "rule": rule}
    log = {"ticker": ticker, "side": side, "shares": shares, "rule": rule, "reason": reason[:300]}

    # 1. Nothing to do
    if risk_output.get("status") == "rejected" or side not in ("buy", "sell") or shares <= 0:
        return {**result, "status": "skipped", "reason": "no order to place"}

    try:
        entry = get_position(ticker).get("avg_entry_price")
        log["entry_price"] = entry

        # 2. Practice mode and the emergency switch: log only
        if practice:
            log_trade({**log, "status": "practice"})
            return {**result, "status": "practice", "reason": f"practice mode: would {side} {shares} {ticker}"}
        if not TRADING_ENABLED:
            log_trade({**log, "status": "disabled"})
            return {**result, "status": "skipped", "reason": "TRADING_ENABLED is off"}

        # 3. Market must be open
        if not get_clock()["is_open"]:
            return {**result, "status": "skipped", "reason": "market closed"}

        # 4. No duplicate orders
        if get_open_orders(ticker):
            return {**result, "status": "skipped", "reason": "open order already exists"}

        # 5. Never sell more than we own (that would be a short)
        if side == "sell":
            owned = int(float(get_position(ticker)["qty"] or 0))
            shares = min(shares, owned)
            if shares <= 0:
                return {**result, "status": "skipped", "reason": "no shares to sell"}

        # 6. Place it, then wait briefly for the fill
        placed = place_order(ticker, side, shares)
        for _ in range(10):
            placed = get_order(placed["id"])
            if placed["status"] in ("filled", "canceled", "rejected", "expired"):
                break
            time.sleep(1)

        fill = placed.get("filled_avg_price")
        log_trade({**log, "shares": shares, "status": placed["status"], "fill_price": fill, "order_id": placed["id"]})
        if placed["status"] in ("filled", "partially_filled"):
            _update_state(ticker, side, shares, rule, reason, fill)

        return {**result, "shares": shares, "status": placed["status"], "order_id": placed["id"],
                "filled_qty": placed.get("filled_qty"), "fill_price": fill}
    except Exception as e:
        log_trade({**log, "status": "error", "reason": str(e)[:300]})
        return {**result, "status": "error", "reason": str(e)}


if __name__ == "__main__":
    import json
    test = {"ticker": "AAPL", "status": "approved", "final_order": {"side": "buy", "shares": 1}}
    print(json.dumps(execute(test, practice=True), indent=2))