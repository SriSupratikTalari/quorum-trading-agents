import os
import json
import time
import requests
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

from agents import news_agent
from orchestrator import run_ticker
from main import save
from tools.trading_tools import get_all_positions,get_clock
from config import CHECK_EVERY_HOURS,NEWS_DROP_TRIGGER,NEWS_LOW_SCORE,MAX_ALERT_RUNS_PER_DAY

load_dotenv()
DATA=Path(__file__).resolve().parent/"data"
SCORES=DATA/"news_scores.json"

def load_scores():
    return json.loads(SCORES.read_text()) if SCORES.exists() else {}

def save_scores(scores):
    DATA.mkdir(exist_ok=True)
    SCORES.write_text(json.dumps(scores,indent=2))

def alert(text):
    """Print, and send to Discord if a webhook is set."""
    print(text)
    url=os.getenv("DISCORD_WEBHOOK_URL")
    if url:
        try:
            requests.post(url,json={"content":text[:1900]},timeout=10)  # Discord limit is 2000 chars
        except Exception as e:
            print(f"alert failed: {e}")

def check_once(runs_today:set):
    scores=load_scores()
    held=[p["ticker"] for p in get_all_positions()]
    market_open=get_clock()["is_open"]

    for ticker in held:
        report=news_agent.run(ticker)
        new=report.get("score")
        if new is None:
            continue
        old=scores.get(ticker)
        scores[ticker]=new

        bad=new<=NEWS_LOW_SCORE or (old is not None and old-new>=NEWS_DROP_TRIGGER)
        if not bad:
            continue

        alert(f"⚠️ {ticker}: news score {old} → {new}\n{report.get('summary','')[:500]}")
        if not market_open:
            alert(f"{ticker}: market closed, the next daily run will review it")
            continue
        if ticker in runs_today or len(runs_today)>=MAX_ALERT_RUNS_PER_DAY:
            alert(f"{ticker}: skipped re-run (daily alert limit)")
            continue

        runs_today.add(ticker)
        state=run_ticker(ticker)
        save(state)
        alert(f"{ticker}: PM {state['decision'].get('action')} | "
              f"Risk {state['risk'].get('status')} | Exec {state['execution'].get('status')}")

    save_scores(scores)

def main():
    runs_today,day=set(),date.today()
    while True:
        if date.today()!=day:          # new day: reset the alert cap
            runs_today,day=set(),date.today()
        try:
            check_once(runs_today)
        except Exception as e:
            alert(f"watcher error: {e}")
        time.sleep(CHECK_EVERY_HOURS*3600)

if __name__=="__main__":
    main()