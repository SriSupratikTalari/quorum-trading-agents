import csv
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from tools.trading_tools import get_clock,get_open_orders,get_position,place_order,get_order
from config import TRADING_ENABLED,MAX_RULE_TRADES_PER_DAY,COOLDOWN_DAYS
from state import load_state,save_state
from alerts import alert

DATA=Path(__file__).resolve().parent.parent/"data"   # agents/ -> repo root -> data
TRADES_PATH=DATA/"trades.csv"
FIELDS=["time","ticker","side","shares","price","trigger","status","detail"]

def log_trade(result:dict)->dict:
    """One row per trade attempt in data/trades.csv. Returns result so it can be used in return."""
    DATA.mkdir(parents=True,exist_ok=True)
    new=not TRADES_PATH.exists()
    with open(TRADES_PATH,"a",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({"time":datetime.now().isoformat(timespec="seconds"),
                    "ticker":result.get("ticker"),"side":result.get("side"),
                    "shares":result.get("shares"),"price":result.get("fill_price") or "",
                    "trigger":result.get("trigger"),"status":result.get("status"),
                    "detail":result.get("reason","")})
    return result

def update_state(ticker,side,price,reason,remaining):
    """Only called after a real fill."""
    s=load_state()
    today=date.today()
    if side=="buy":
        s["buy_dates"].setdefault(ticker,today.isoformat())
        if price:
            s["peaks"].setdefault(ticker,price)
    elif side=="sell" and remaining is not None and remaining<=0:
        for key in ("peaks","buy_dates","below_stop"):   # fully sold: forget it
            s[key].pop(ticker,None)
    if reason!="pm":
        s["rule_trades_today"]["count"]+=1
        if side=="sell":
            s["cooldowns"][ticker]=(today+timedelta(days=COOLDOWN_DAYS)).isoformat()
    save_state(s)

def execute(risk_output:dict,reason="pm",practice=False)->dict:
    ticker=risk_output["ticker"]
    order=risk_output.get("final_order") or {}
    side,shares=order.get("side"),int(order.get("shares") or 0)
    result={"agent":"execution","ticker":ticker,"side":side,"shares":shares,"trigger":reason}

    # 1. Nothing to do (not logged, or every "hold" would fill the log)
    if risk_output.get("status")=="rejected" or side not in ("buy","sell") or shares<=0:
        return {**result,"status":"skipped","reason":"no order to place"}

    # 2. Safety switches
    if not TRADING_ENABLED:
        return log_trade({**result,"status":"disabled","reason":"TRADING_ENABLED is False"})
    if reason!="pm" and load_state()["rule_trades_today"]["count"]>=MAX_RULE_TRADES_PER_DAY:
        alert(f"🚨 {ticker}: daily rule-trade cap hit, skipped {side} ({reason})")
        return log_trade({**result,"status":"capped","reason":"daily rule-trade cap hit"})
    if practice:
        alert(f"🧪 practice: would {side} {shares} {ticker} ({reason})")
        return log_trade({**result,"status":"practice","reason":f"would {side} {shares} {ticker}"})

    try:
        # 3. Market must be open
        if not get_clock()["is_open"]:
            return log_trade({**result,"status":"skipped","reason":"market closed"})

        # 4. No duplicate orders
        if get_open_orders(ticker):
            return log_trade({**result,"status":"skipped","reason":"open order already exists"})

        # 5. Never sell more than we own (that would be a short)
        owned=None
        if side=="sell":
            owned=int(float(get_position(ticker)["qty"]))
            shares=min(shares,owned)
            if shares<=0:
                return log_trade({**result,"status":"skipped","reason":"no shares to sell"})

        # 6. Place it, then wait briefly for the fill
        placed=place_order(ticker,side,shares)
        for _ in range(10):
            placed=get_order(placed["id"])
            if placed["status"] in ("filled","canceled","rejected","expired"):
                break
            time.sleep(1)

        filled=int(float(placed.get("filled_qty") or 0))
        price=float(placed["filled_avg_price"]) if placed.get("filled_avg_price") else None
        out={**result,"shares":shares,"status":placed["status"],"order_id":placed["id"],
             "filled_qty":filled,"fill_price":price}

        # 7. Remember it (only if something actually filled)
        if filled>0:
            remaining=owned-filled if owned is not None else None
            update_state(ticker,side,price,reason,remaining)
        return log_trade(out)
    except Exception as e:
        return log_trade({**result,"status":"error","reason":str(e)})

if __name__=="__main__":
    import json
    test={"ticker":"AAPL","status":"approved","final_order":{"side":"buy","shares":1}}
    print(json.dumps(execute(test),indent=2))
    