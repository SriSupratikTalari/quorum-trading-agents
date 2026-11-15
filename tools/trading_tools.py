"""
trading_tools.py
Tools that read and write the Alpaca PAPER trading account.

Used by:
  - PM (get_portfolio_context), Risk, Execution, rules, price guard, bench
"""
import os
from datetime import date, datetime

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://paper-api.alpaca.markets/v2"  # PAPER account: fake money
HEADERS = {
    "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
    "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY"),
}


def _get(path: str):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    return r


def _f(x):
    """Alpaca returns numbers as strings, e.g. "101500.25". Convert safely."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def get_account() -> dict:
    """Cash and total value of the paper account."""
    r = _get("/account")
    r.raise_for_status()
    a = r.json()
    return {
        "cash": _f(a.get("cash")),
        "equity": _f(a.get("equity")),            # cash + value of all positions
        "buying_power": _f(a.get("buying_power")),
        "trading_blocked": a.get("trading_blocked", False),
    }


def get_position(ticker: str, equity: float | None = None) -> dict:
    """Current holding in one stock. Not holding it is normal -> qty 0 (Alpaca returns 404)."""
    ticker = ticker.upper()
    r = _get(f"/positions/{ticker}")

    if r.status_code == 404:  # we don't own it
        return {"ticker": ticker, "qty": 0.0, "market_value": 0.0, "avg_entry_price": None,
                "current_price": None, "unrealized_pl_pct": None, "weight": 0.0}
    r.raise_for_status()

    p = r.json()
    market_value = _f(p.get("market_value")) or 0.0
    if equity is None:
        equity = get_account()["equity"]

    return {
        "ticker": ticker,
        "qty": _f(p.get("qty")),
        "market_value": market_value,
        "avg_entry_price": _f(p.get("avg_entry_price")),
        "current_price": _f(p.get("current_price")),
        "unrealized_pl_pct": _f(p.get("unrealized_plpc")),   # e.g. 0.05 = up 5%
        "weight": round(market_value / equity, 4) if equity else 0.0,  # share of the whole portfolio
    }


def get_all_positions() -> list:
    """Every stock currently held."""
    r = _get("/positions")
    r.raise_for_status()
    return [{"ticker": p["symbol"],
             "qty": _f(p.get("qty")),
             "market_value": _f(p.get("market_value")),
             "avg_entry_price": _f(p.get("avg_entry_price")),
             "current_price": _f(p.get("current_price")),
             "unrealized_pl_pct": _f(p.get("unrealized_plpc"))}
            for p in r.json()]


def get_portfolio_context(ticker: str) -> dict:
    """Everything the PM needs to know about the portfolio."""
    account = get_account()
    position = get_position(ticker, equity=account["equity"])
    return {
        "account": account,
        "position": position,
        "cash_weight": round(account["cash"] / account["equity"], 4) if account["equity"] else None,
    }


def get_clock() -> dict:
    r = requests.get(f"{BASE_URL}/clock", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()  # includes "is_open"


def get_open_orders(ticker: str) -> list:
    r = requests.get(f"{BASE_URL}/orders", headers=HEADERS,
                     params={"status": "open", "symbols": ticker}, timeout=15)
    r.raise_for_status()
    return r.json()


def place_order(ticker: str, side: str, shares: int) -> dict:
    # Unique per second, so a later run the same day (e.g. the price guard) can still place an order
    client_id = f"quorum-{ticker}-{side}-{datetime.now():%Y%m%d-%H%M%S}"
    body = {"symbol": ticker, "qty": str(shares), "side": side, "type": "market",
            "time_in_force": "day", "client_order_id": client_id}
    r = requests.post(f"{BASE_URL}/orders", headers=HEADERS, json=body, timeout=15)
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text}")   # shows Alpaca's real reason
    return r.json()


def get_order(order_id: str) -> dict:
    r = requests.get(f"{BASE_URL}/orders/{order_id}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def get_portfolio_history(period: str = "3M") -> dict:
    r = requests.get(f"{BASE_URL}/account/portfolio/history", headers=HEADERS,
                     params={"period": period, "timeframe": "1D"}, timeout=15)
    r.raise_for_status()
    equity = [e for e in r.json()["equity"] if e]  # drop empty days before the account was funded
    if not equity:
        return {"equity": [], "peak": None, "drawdown": 0.0}
    peak = max(equity)
    return {"equity": equity, "peak": peak, "drawdown": round(equity[-1] / peak - 1, 4)}


if __name__ == "__main__":
    import json
    print(json.dumps(get_portfolio_context("AAPL"), indent=2))