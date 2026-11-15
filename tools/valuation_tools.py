"""
valuation_tools.py
Is the stock cheap or expensive, and when does it report earnings? Numbers only, no LLM.
yfinance is unofficial and can break, so callers wrap these in try/except.
"""
from datetime import date, datetime

import yfinance as yf

from tools.cache_utils import daily_cache


@daily_cache
def get_valuation(ticker: str) -> dict:
    info = yf.Ticker(ticker).info
    price, target = info.get("currentPrice"), info.get("targetMeanPrice")
    return {
        "price": price,
        "trailing_pe": info.get("trailingPE"),          # price vs last year's earnings
        "forward_pe": info.get("forwardPE"),            # price vs next year's expected earnings
        "peg_ratio": info.get("trailingPegRatio"),      # P/E adjusted for growth (~1 = fair)
        "price_to_sales": info.get("priceToSalesTrailing12Months"),
        "ev_to_ebitda": info.get("enterpriseToEbitda"),
        "analyst_target": target,
        "upside_to_target": round(target / price - 1, 4) if price and target else None,
        "analyst_rating": info.get("recommendationKey"),
        "n_analysts": info.get("numberOfAnalystOpinions"),
    }


@daily_cache
def get_next_earnings(ticker: str):
    """Next earnings date as 'YYYY-MM-DD', or None if unknown."""
    t = yf.Ticker(ticker)
    try:
        cal = t.calendar or {}
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        upcoming = sorted(str(d)[:10] for d in (dates or []) if str(d)[:10] >= date.today().isoformat())
        if upcoming:
            return upcoming[0]
    except Exception:
        pass
    ts = (t.info or {}).get("earningsTimestamp")
    if ts:
        d = datetime.fromtimestamp(ts).date().isoformat()
        return d if d >= date.today().isoformat() else None
    return None


def days_to_earnings(ticker: str):
    """Days until the next earnings report, or None if unknown."""
    try:
        d = get_next_earnings(ticker)
    except Exception:
        return None
    return (date.fromisoformat(d) - date.today()).days if d else None


if __name__ == "__main__":
    import json
    print(json.dumps(get_valuation("AAPL"), indent=2))
    print("next earnings:", get_next_earnings("AAPL"), "| days:", days_to_earnings("AAPL"))