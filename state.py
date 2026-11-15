import json
import os
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent/"data"
STATE_PATH = DATA/"state.json"

def default_state():
    return {
        "peaks": {},              # ticker -> highest price since buying
        "buy_dates": {},          # ticker -> date bought
        "below_stop": {},         # ticker -> checks in a row below the stop
        "cooldowns": {},          # ticker -> date cooldown ends
        "rule_trades_today": {"date": date.today().isoformat(), "count": 0},
        "last_news_run": {},      # ticker -> time News agent last ran
        "bench_order": [],        # tickers, best first (Step 9)
    }

def load_state():
    state = default_state()
    if STATE_PATH.exists():
        saved = json.loads(STATE_PATH.read_text())
        state.update(saved)       # saved values win, missing keys keep defaults

    today = date.today().isoformat()
    if state["rule_trades_today"].get("date") != today:
        state["rule_trades_today"] = {"date": today, "count": 0}   # new day: reset
    return state

def save_state(state):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    os.replace(tmp, STATE_PATH)   # swap in one step, so the file is never half-written
