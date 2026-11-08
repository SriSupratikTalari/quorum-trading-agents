import time
from tools.trading_tools import get_clock,get_open_orders,get_position,place_order,get_order

def execute(risk_output:dict)->dict:
    ticker=risk_output["ticker"]
    order=risk_output.get("final_order") or {}
    side,shares=order.get("side"),int(order.get("shares") or 0)
    result={"agent":"execution","ticker":ticker,"side":side,"shares":shares}

    # 1. Nothing to do
    if risk_output.get("status")=="rejected" or side not in ("buy","sell") or shares<=0:
        return {**result,"status":"skipped","reason":"no order to place"}

    try:
        # 2. Market must be open
        if not get_clock()["is_open"]:
            return {**result,"status":"skipped","reason":"market closed"}

        # 3. No duplicate orders
        if get_open_orders(ticker):
            return {**result,"status":"skipped","reason":"open order already exists"}

        # 4. Never sell more than we own (that would be a short)
        if side=="sell":
            owned=int(float(get_position(ticker)["qty"]))
            shares=min(shares,owned)
            if shares<=0:
                return {**result,"status":"skipped","reason":"no shares to sell"}

        # 5. Place it, then wait briefly for the fill
        placed=place_order(ticker,side,shares)
        for _ in range(10):
            placed=get_order(placed["id"])
            if placed["status"] in ("filled","canceled","rejected","expired"):
                break
            time.sleep(1)

        return {**result,"shares":shares,"status":placed["status"],"order_id":placed["id"],
                "filled_qty":placed.get("filled_qty"),"fill_price":placed.get("filled_avg_price")}
    except Exception as e:
        return {**result,"status":"error","reason":str(e)}

if __name__=="__main__":
    import json
    test={"ticker":"AAPL","status":"approved","final_order":{"side":"buy","shares":1}}
    print(json.dumps(execute(test),indent=2))