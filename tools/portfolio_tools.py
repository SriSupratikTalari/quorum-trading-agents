"""
portfolio_tools.py
Tools the Portfolio Manager can call itself.
"""
import os
import math

import requests
from dotenv import load_dotenv

from tools.trading_tools import get_account, get_position, get_portfolio_context

load_dotenv()

DATA_URL = "https://data.alpaca.markets/v2"
HEADERS = {
    "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
    "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY"),
}
MAX_WEIGHT = 0.10        # no stock above 10% of the portfolio (Risk agent enforces this too)
MIN_TRADE_VALUE = 100.0  # skip tiny trades that aren't worth placing


def get_latest_price(ticker: str) -> dict:
    """Latest trade price. feed=iex works on the free plan."""
    ticker = ticker.upper()
    r = requests.get(f"{DATA_URL}/stocks/{ticker}/trades/latest",
                     headers=HEADERS, params={"feed": "iex"}, timeout=15)
    r.raise_for_status()
    t = r.json()["trade"]
    return {"ticker": ticker, "price": float(t["p"]), "time": t["t"]}


def compute_order_size(ticker: str, target_weight: float) -> dict:
    """Turn 'I want AAPL at 6% of the portfolio' into a buy/sell of N shares."""
    ticker = ticker.upper()
    target_weight = max(0.0, min(target_weight, MAX_WEIGHT))  # clamp to 0-10%

    account = get_account()
    position = get_position(ticker, equity=account["equity"])
    price = position["current_price"] or get_latest_price(ticker)["price"]

    target_value = target_weight * account["equity"]
    delta_value = target_value - position["market_value"]  # + = buy more, - = sell some

    if target_weight == 0 and position["qty"] > 0:
        shares, side = position["qty"], "sell"           # exit the whole position
    else:
        shares = math.floor(abs(delta_value) / price)    # whole shares only
        side = "buy" if delta_value > 0 else "sell"

    if shares == 0 or abs(delta_value) < MIN_TRADE_VALUE:
        side, shares = "none", 0

    if side == "buy" and shares * price > account["cash"]:  # can't spend cash we don't have
        shares = math.floor(account["cash"] / price)

    return {
        "ticker": ticker,
        "price": price,
        "current_weight": position["weight"],
        "target_weight": target_weight,
        "side": side,
        "shares": shares,
        "est_value": round(shares * price, 2),
    }


portfolio_manager_tools_schema = [
    {
        "type": "function",
        "name": "get_portfolio_context",
        "description": "Get cash, total equity, and the current position and portfolio weight for this stock. "
                       "Call this before deciding, so you know what is already owned.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker, e.g. 'AAPL'"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_latest_price",
        "description": "Get the latest trade price of the stock.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker, e.g. 'AAPL'"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "compute_order_size",
        "description": "Preview what a target portfolio weight means in shares (buy/sell/none). "
                       "Use this instead of calculating shares yourself.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker, e.g. 'AAPL'"},
                "target_weight": {"type": "number", "description": f"Target share of the portfolio, 0 to {MAX_WEIGHT}"},
            },
            "required": ["ticker", "target_weight"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

portfolio_manager_tools = {
    "get_portfolio_context": get_portfolio_context,
    "get_latest_price": get_latest_price,
    "compute_order_size": compute_order_size,
}