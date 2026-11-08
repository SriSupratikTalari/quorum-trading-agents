import os
import requests
import yfinance as yf
from datetime import date,timedelta
from dotenv import load_dotenv
from tools.technical_tools import get_technicals,get_relative_strength

load_dotenv()

def get_fred_series(series_id:str,days:int=400)->list:
    url='https://api.stlouisfed.org/fred/series/observations'
    start=(date.today()-timedelta(days=days)).isoformat()
    params={'series_id':series_id,'api_key':os.getenv('fred_api'),
            'file_type':'json','observation_start':start}
    r=requests.get(url,params=params,timeout=15)
    r.raise_for_status()
    return [{"date":o["date"],"value":float(o["value"])}
            for o in r.json()["observations"] if o["value"]!="."]

def get_macro_data(days=400):
    SERIES={
        "fed_funds_rate":"FEDFUNDS",
        "treasury_10y":"DGS10",
        "yield_curve_10y_2y":"T10Y2Y",
        "cpi_index":"CPIAUCSL",
        "unemployment_rate":"UNRATE",
        "vix":"VIXCLS",
    }
    year_ago=(date.today()-timedelta(days=365)).isoformat()
    out={}
    for name,series_id in SERIES.items():
        obs=get_fred_series(series_id,days=500)
        old=[o for o in obs if o["date"]<=year_ago][-1]
        out[name]={"latest":obs[-1]["value"],
                   "as_of":obs[-1]["date"],
                   "change_1y":round(obs[-1]["value"]-old["value"],2)}
    # Turn the CPI index into yearly inflation %
    out["inflation_pct"]=round((out["cpi_index"]["latest"]/(out["cpi_index"]["latest"]-out["cpi_index"]["change_1y"])-1)*100,2)
    out["yield_curve_inverted"]=out["yield_curve_10y_2y"]["latest"]<0
    return out

# ---------------- NEW ----------------

def get_market_trend()->dict:
    """Is the overall market (SPY) in an uptrend or downtrend?"""
    return get_technicals("SPY")

SECTOR_ETFS={
    "Technology":"XLK","Financial Services":"XLF","Healthcare":"XLV",
    "Consumer Cyclical":"XLY","Consumer Defensive":"XLP","Energy":"XLE",
    "Industrials":"XLI","Utilities":"XLU","Real Estate":"XLRE",
    "Basic Materials":"XLB","Communication Services":"XLC",
}

def get_sector_context(ticker:str)->dict:
    """The stock's sector, how that sector is doing vs SPY, and how much the stock swings with the market."""
    info=yf.Ticker(ticker).info
    sector=info.get("sector")
    etf=SECTOR_ETFS.get(sector)
    rs=get_relative_strength(etf) if etf else None
    return {"ticker":ticker.upper(),
            "sector":sector,
            "beta":info.get("beta"),
            "sector_etf":etf,
            "sector_vs_spy_90d":{"sector_return":rs["stock_return"],
                                 "spy_return":rs["spy_return"],
                                 "sector_outperformance":rs["outperformance"]} if rs else None}
RELEASES={"cpi":10,"jobs_report":50,"gdp":53}

def get_upcoming_releases()->dict:
    """Next scheduled dates for big economic reports."""
    out={}
    for name,release_id in RELEASES.items():
        params={'release_id':release_id,'api_key':os.getenv('fred_api'),'file_type':'json',
                'include_release_dates_with_no_data':'true','sort_order':'asc',
                'realtime_start':date.today().isoformat()}
        r=requests.get('https://api.stlouisfed.org/fred/release/dates',params=params,timeout=15)
        r.raise_for_status()
        dates=[d["date"] for d in r.json()["release_dates"] if d["date"]>=date.today().isoformat()]
        out[name]=dates[0] if dates else None
    return out

# ---------------- SCHEMA ----------------

Macro_tools_schema=[
    {
        "type":"function",
        "name":"get_macro_data",
        "description":"US economy snapshot from FRED: Fed rate, 10-year yield, yield curve "
                      "(and whether it is inverted), inflation %, unemployment, and VIX, each with its 1-year change.",
        "parameters":{
            "type":"object",
            "properties":{},
            "required":[],
            "additionalProperties":False,
        },
        "strict":True,
    },
    {
        "type":"function",
        "name":"get_market_trend",
        "description":"Price, 50/200-day averages, and RSI for SPY: is the overall market trending up or down.",
        "parameters":{
            "type":"object",
            "properties":{},
            "required":[],
            "additionalProperties":False,
        },
        "strict":True,
    },
    {
        "type":"function",
        "name":"get_sector_context",
        "description":"The stock's sector, its beta (how much it swings with the market), "
                      "and how its sector has done vs SPY over 90 trading days.",
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
        "name":"get_upcoming_releases",
        "description":"Next scheduled dates for the CPI, jobs, and GDP reports, which often move the market.",
        "parameters":{
            "type":"object",
            "properties":{},
            "required":[],
            "additionalProperties":False,
        },
        "strict":True,
    },
]
macro_tools={
    "get_macro_data":get_macro_data,
    "get_market_trend":get_market_trend,
    "get_sector_context":get_sector_context,
    "get_upcoming_releases":get_upcoming_releases,
}

if __name__=="__main__":
    import json
    print(json.dumps(get_macro_data(),indent=2))
    print(json.dumps(get_sector_context("AAPL"),indent=2,default=str))
    print(json.dumps(get_upcoming_releases(),indent=2))