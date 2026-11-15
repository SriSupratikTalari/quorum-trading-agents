import math
import yfinance as yf
from functools import lru_cache

import state
from config import (MAX_POSITION_WEIGHT, MIN_CASH_WEIGHT, MAX_SECTOR_WEIGHT,
                    MIN_CONFIDENCE, HIGH_VOLATILITY, MAX_DRAWDOWN, EARNINGS_BLOCK_DAYS)
from tools.trading_tools import (get_account, get_all_positions, get_clock,
                                 get_open_orders, get_portfolio_history)
from tools.portfolio_tools import compute_order_size
from tools.valuation_tools import days_to_earnings

NO_ORDER = {"side": "none", "shares": 0}


@lru_cache(maxsize=None)
def _sector(ticker):
    try:
        return yf.Ticker(ticker).info.get("sector")
    except Exception:
        return None


def risk_check(pm_decision: dict, research: dict) -> dict:
    ticker = pm_decision["ticker"].upper()
    checks = []
    original = NO_ORDER

    def check(rule, passed, note=None, info=False):
        show = note and (not passed or info)   # failure reason, or an info note on a pass
        checks.append({"rule": rule, "passed": passed, **({"note": note} if show else {})})
        return passed

    def result(status, final):
        return {"agent": "risk", "ticker": ticker, "status": status,
                "original_order": original, "final_order": final, "checks": checks}

    # Hold = nothing to check
    if pm_decision.get("action") == "hold":
        return result("approved", NO_ORDER)

    try:
        # Turn target_weight into shares (Python math, same as the PM preview)
        sized = compute_order_size(ticker, pm_decision["target_weight"])
        side, shares, price = sized["side"], sized["shares"], sized["price"]
        original = {"side": side, "shares": shares}
        if side == "none":
            return result("approved", NO_ORDER)

        # ---- Rules for ALL orders ----
        if not check("action_matches", side == pm_decision["action"],
                     f"PM said {pm_decision['action']} but target weight means {side}"):
            return result("rejected", NO_ORDER)
        account = get_account()
        if not check("account_ok", not account["trading_blocked"], "trading is blocked"):
            return result("rejected", NO_ORDER)
        if not check("market_open", get_clock()["is_open"], "market is closed"):
            return result("rejected", NO_ORDER)
        if not check("no_duplicates", not get_open_orders(ticker), "an order is already open"):
            return result("rejected", NO_ORDER)

        # Sells stop here: never trap the portfolio in a losing position
        if side == "sell":
            return result("approved", original)

        # ---- Rules for BUYS only ----
        until = state.cooldown_until(ticker)
        if not check("cooldown", until is None, f"a rule sold {ticker} recently; no rebuy until after {until}"):
            return result("rejected", NO_ORDER)
        dte = days_to_earnings(ticker)
        if not check("earnings_block", dte is None or not (0 <= dte <= EARNINGS_BLOCK_DAYS),
                     f"earnings in {dte} days"):
            return result("rejected", NO_ORDER)
        if dte is None:
            check("earnings_block", True, "earnings date unknown, rule skipped", info=True)

        conf = pm_decision.get("confidence", 0)
        if not check("min_confidence", conf >= MIN_CONFIDENCE, f"confidence {conf} < {MIN_CONFIDENCE}"):
            return result("rejected", NO_ORDER)
        dd = get_portfolio_history()["drawdown"]
        if not check("drawdown_brake", dd > -MAX_DRAWDOWN, f"portfolio down {dd:.1%} from peak"):
            return result("rejected", NO_ORDER)

        equity, cash = account["equity"], account["cash"]
        positions = get_all_positions()

        def cap(rule, limit, note):
            nonlocal shares
            limit = max(limit, 0)
            ok = shares <= limit
            check(rule, ok, None if ok else f"{note}: {shares} → {limit} shares")
            shares = min(shares, limit)

        # Max position size
        held = sum(p["market_value"] for p in positions if p["ticker"] == ticker)
        cap("max_position", math.floor((MAX_POSITION_WEIGHT * equity - held) / price),
            f"{ticker} would pass {MAX_POSITION_WEIGHT:.0%}")

        # Min cash
        cap("min_cash", math.floor((cash - MIN_CASH_WEIGHT * equity) / price),
            f"must keep {MIN_CASH_WEIGHT:.0%} cash")

        # Max sector exposure
        sector = _sector(ticker)
        if sector:
            in_sector = sum(p["market_value"] for p in positions if _sector(p["ticker"]) == sector)
            cap("max_sector", math.floor((MAX_SECTOR_WEIGHT * equity - in_sector) / price),
                f"{sector} would pass {MAX_SECTOR_WEIGHT:.0%}")
        else:
            check("max_sector", True, "sector unknown, rule skipped", info=True)

        # Volatility
        vol = research.get("technical", {}).get("key_metrics", {}).get("volatility_20d")
        if vol is not None and vol > 1:
            vol /= 100  # handle 55 vs 0.55
        if vol is not None and vol > HIGH_VOLATILITY:
            check("volatility", False, f"volatility {vol:.0%} → size halved: {shares} → {shares // 2}")
            shares //= 2
        else:
            check("volatility", True, None if vol is not None else "no volatility data", info=True)

        if shares <= 0:
            return result("rejected", NO_ORDER)
        final = {"side": "buy", "shares": shares}
        return result("approved" if final == original else "modified", final)

    except Exception as e:
        # If we can't verify safety, don't trade
        check("error", False, str(e))
        return result("rejected", NO_ORDER)


if __name__ == "__main__":
    import json
    pm = {"ticker": "AAPL", "action": "buy", "target_weight": 0.06, "confidence": 7}
    research = {"technical": {"key_metrics": {"volatility_20d": 0.65}}}   # 0.65 > 50% -> size halved
    print(json.dumps(risk_check(pm, research), indent=2))