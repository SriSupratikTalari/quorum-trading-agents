import os
import requests
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv

from tools.cache_utils import daily_cache

load_dotenv()
headers = {"accept": "application/json",
           "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
           "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY")}


def get_price_bars(ticker: str, days: int) -> list:
    url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars"
    start = (date.today() - timedelta(days=int(days * 1.5))).isoformat()
    params = {"timeframe": "1Day", "start": start, "limit": 1000, "adjustment": "all", "feed": "iex", "sort": "asc"}
    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    return response.json()["bars"][-days:]


def compute_indicators(bars: list) -> dict:
    df = pd.DataFrame(bars)
    sma_50 = df["c"].rolling(50).mean()
    sma_200 = df["c"].rolling(200).mean()
    delta = df["c"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss)
    price = df["c"].iloc[-1]
    return {"price": float(price),
            "sma_50": round(float(sma_50.iloc[-1]), 2),
            "sma_200": round(float(sma_200.iloc[-1]), 2),
            "above_sma_50": bool(price > sma_50.iloc[-1]),
            "above_sma_200": bool(price > sma_200.iloc[-1]),
            "rsi_14": round(float(rsi.iloc[-1]), 2),
            "volatility_20d": round(float(df["c"].pct_change().rolling(20).std().iloc[-1] * 252 ** 0.5), 4)}


def get_relative_strength(ticker: str, days: int = 90) -> dict:
    stock = get_price_bars(ticker, days)
    spy = get_price_bars("SPY", days)
    stock_return = stock[-1]["c"] / stock[0]["c"] - 1
    spy_return = spy[-1]["c"] / spy[0]["c"] - 1
    return {"stock_return": round(stock_return, 4),
            "spy_return": round(spy_return, 4),
            "outperformance": round(stock_return - spy_return, 4)}


def get_technicals(ticker: str) -> dict:
    return compute_indicators(get_price_bars(ticker, 300))


# ---------------- FAST CHECKS (no LLM, used by rules, price guard, bench) ----------------

@daily_cache
def get_quick_check(ticker: str) -> dict:
    """Trend, RSI, volatility and 90-day strength. Cached for the day."""
    ind = get_technicals(ticker)
    rs = get_relative_strength(ticker)
    return {"ticker": ticker.upper(), **ind, "outperformance": rs["outperformance"]}


def get_volatility(ticker: str):
    try:
        return get_quick_check(ticker)["volatility_20d"]
    except Exception:
        return None


def get_snapshot(ticker: str) -> dict:
    """Latest price, today's open and yesterday's close (for the gap rule). Not cached."""
    r = requests.get(f"https://data.alpaca.markets/v2/stocks/{ticker}/snapshot",
                     headers=headers, params={"feed": "iex"}, timeout=15)
    r.raise_for_status()
    s = r.json()
    return {"price": (s.get("latestTrade") or {}).get("p"),
            "open": (s.get("dailyBar") or {}).get("o"),
            "prev_close": (s.get("prevDailyBar") or {}).get("c")}


Technical_tools_schema = [
    {
        "type": "function",
        "name": "get_technicals",
        "description": "Get the stock's price, 50-day and 200-day moving averages, 14-day RSI, and volatility.",
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
        "name": "get_relative_strength",
        "description": "Compare the stock's return to SPY over the last 90 trading days.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker, e.g. 'AAPL'"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

technical_tools = {
    "get_technicals": get_technicals,
    "get_relative_strength": get_relative_strength,
}

if __name__ == "__main__":
    import json
    print(json.dumps(get_quick_check("AAPL"), indent=2))
    print(json.dumps(get_snapshot("AAPL"), indent=2))