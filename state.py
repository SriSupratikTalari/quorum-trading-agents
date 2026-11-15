"""
state.py
Quorum's memory between runs, saved in data/state.json:
peaks, buy dates, stop counters, cooldowns, rule-trade counts, News agent timing,
pending news sells, and the active / bench lists.

Usage:
    with state.edit() as s:      # locked read-modify-write (safe with main.py + price_guard.py running)
        s["cooldowns"]["NVDA"] = "2026-11-20"
    s = state.load()              # read-only snapshot

NEVER call execute() or anything else that edits state INSIDE an edit() block (it would deadlock).
"""
import json
import fcntl
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from config import UNIVERSE, BENCH, COOLDOWN_DAYS, NEWS_MIN_MINUTES_BETWEEN_RUNS, MAX_ALERT_RUNS_PER_DAY

DATA = Path(__file__).resolve().parent / "data"
PATH = DATA / "state.json"
LOCK = DATA / "state.lock"


def today() -> str:
    return date.today().isoformat()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default() -> dict:
    return {
        "positions": {},            # ticker -> {entry, peak, buy_date, below_stop_count}
        "cooldowns": {},            # ticker -> "YYYY-MM-DD" (no buys until after this date)
        "rule_trades": {"date": "", "count": 0},
        "alert_runs": {"date": "", "tickers": []},
        "recent_rule_trades": [],   # last ~50 rule trades, shown to the PM
        "last_news_run": {},        # ticker -> time the News agent last ran (price guard)
        "last_news_score": {},      # ticker -> last News agent score
        "last_headline_check": {},  # ticker -> time headlines were last checked
        "pending_news_sells": {},   # ticker -> {alert_price, alert_time, reason}
        "active": list(UNIVERSE),
        "bench": list(BENCH),
        "sold": {},                 # ticker -> date it was fully sold and moved to the bench
        "bench_last_run": "",
    }


def _read() -> dict:
    s = json.loads(PATH.read_text()) if PATH.exists() else {}
    for k, v in _default().items():
        s.setdefault(k, v)
    return s


def load() -> dict:
    """Read-only snapshot. Changes made to it are NOT saved."""
    return _read()


@contextmanager
def edit():
    """Locked read-modify-write. Saved only if the block finishes without an error."""
    DATA.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = _read()
        yield s
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=2, default=str))
        tmp.replace(PATH)


# ---------------- COOLDOWN ----------------

def set_cooldown(s: dict, ticker: str, days: int = COOLDOWN_DAYS):
    s["cooldowns"][ticker] = (date.today() + timedelta(days=days)).isoformat()


def cooldown_until(ticker: str, s: dict | None = None):
    """Returns the end date if the stock is in cooldown, else None."""
    s = s or load()
    until = s["cooldowns"].get(ticker.upper())
    return until if until and until >= today() else None


# ---------------- RULE TRADES ----------------

def rule_trades_today(s: dict) -> int:
    rt = s["rule_trades"]
    return rt["count"] if rt["date"] == today() else 0


def add_rule_trade(s: dict, record: dict):
    if s["rule_trades"]["date"] != today():
        s["rule_trades"] = {"date": today(), "count": 0}
    s["rule_trades"]["count"] += 1
    s["recent_rule_trades"] = (s["recent_rule_trades"] + [record])[-50:]


def recent_rule_trades(ticker: str, days: int = 14, s: dict | None = None) -> list:
    s = s or load()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [t for t in s["recent_rule_trades"] if t.get("ticker") == ticker.upper() and t.get("date", "") >= cutoff]


# ---------------- NEWS TIMING ----------------

def can_run_news(s: dict, ticker: str) -> bool:
    last = s["last_news_run"].get(ticker)
    if not last:
        return True
    return datetime.now() - datetime.fromisoformat(last) >= timedelta(minutes=NEWS_MIN_MINUTES_BETWEEN_RUNS)


def can_alert_run(s: dict, ticker: str) -> bool:
    ar = s["alert_runs"]
    if ar["date"] != today():
        return True
    return ticker not in ar["tickers"] and len(ar["tickers"]) < MAX_ALERT_RUNS_PER_DAY


def add_alert_run(s: dict, ticker: str):
    if s["alert_runs"]["date"] != today():
        s["alert_runs"] = {"date": today(), "tickers": []}
    s["alert_runs"]["tickers"].append(ticker)


# ---------------- ACTIVE / BENCH ----------------

def move_to_bench(s: dict, ticker: str):
    """A fully sold stock leaves the active list and goes to the end of the bench."""
    ticker = ticker.upper()
    if ticker in s["active"]:
        s["active"].remove(ticker)
    if ticker not in s["bench"]:
        s["bench"].append(ticker)
    s["sold"][ticker] = today()
    s["positions"].pop(ticker, None)


def move_to_active(s: dict, ticker: str):
    ticker = ticker.upper()
    if ticker in s["bench"]:
        s["bench"].remove(ticker)
    if ticker not in s["active"]:
        s["active"].append(ticker)
    s["sold"].pop(ticker, None)