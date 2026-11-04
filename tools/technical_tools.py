import os
import requests
import pandas as pd
from datetime import date,timedelta
from dotenv import load_dotenv

load_dotenv()
headers={"accept":"application/json",
         "APCA-API-KEY-ID":os.getenv("ALPACA_API_KEY"),
         "APCA-API-SECRET-KEY":os.getenv("ALPACA_SECRET_KEY")}

def get_price_bars(ticker:str,days:int)->list:
    url=f"https://data.alpaca.markets/v2/stocks/{ticker}/bars"
    start=(date.today()-timedelta(days=int(days*1.5))).isoformat()
    params={"timeframe":"1Day","start":start,"limit":1000,"adjustment":"all","feed":"iex","sort":"asc"}
    response=requests.get(url,headers=headers,params=params)
    response.raise_for_status()
    return response.json()["bars"][-days:]

def compute_indicators(bars:list)->dict:
    df=pd.DataFrame(bars)
    sma_50=df["c"].rolling(50).mean()
    sma_200=df["c"].rolling(200).mean()
    delta=df["c"].diff()
    gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-100/(1+gain/loss)
    return {"price":df["c"].iloc[-1],
            "sma_50":round(sma_50.iloc[-1],2),
            "sma_200":round(sma_200.iloc[-1],2),
            "rsi_14":round(rsi.iloc[-1],2)}

def get_relative_strength(ticker:str,days:int=90)->dict:
    stock=get_price_bars(ticker,days)
    spy=get_price_bars("SPY",days)
    stock_return=stock[-1]["c"]/stock[0]["c"]-1
    spy_return=spy[-1]["c"]/spy[0]["c"]-1
    return {"stock_return":round(stock_return,4),
            "spy_return":round(spy_return,4),
            "outperformance":round(stock_return-spy_return,4)}

def get_technicals(ticker:str)->dict:
    return compute_indicators(get_price_bars(ticker,300))

Technical_tools_schema=[
    {
        "type":"function",
        "name":"get_technicals",
        "description":"Get the stock's price, 50-day and 200-day moving averages, and 14-day RSI.",
        "parameters":{
            "type":"object",
            "properties":{"ticker":{"type":"string","description":"Stock ticker, e.g. 'AAPL'"}},
            "required":["ticker"],
            "additionalProperties":False,
        },
        "strict":True,
    },
    {
        "type":"function",
        "name":"get_relative_strength",
        "description":"Compare the stock's return to SPY over the last 90 trading days.",
        "parameters":{
            "type":"object",
            "properties":{"ticker":{"type":"string","description":"Stock ticker, e.g. 'AAPL'"}},
            "required":["ticker"],
            "additionalProperties":False,
        },
        "strict":True,
    },
]

technical_tools={
    "get_technicals":get_technicals,
    "get_relative_strength":get_relative_strength,
}
