"""
config.py
Every tunable setting in one place. Change ONE setting at a time and log it in CHANGELOG.md.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------- EMERGENCY OFF SWITCH ----------------
# Set TRADING_ENABLED=false in .env on the server to stop ALL orders instantly (no git push needed).
TRADING_ENABLED = os.getenv("TRADING_ENABLED", "true").lower() == "true"

# ---------------- STOCK UNIVERSE ----------------
# Starting "active" list. After the first run, the live lists are kept in data/state.json.
UNIVERSE = [
    "AAPL", "MSFT", "NVDA",          # Technology
    "GOOGL", "META",                 # Communication
    "AMZN", "TSLA", "COST", "PG",    # Consumer
    "JPM", "V",                      # Financials
    "UNH", "LLY", "JNJ",             # Healthcare
    "XOM", "CVX",                    # Energy
    "CAT", "GE",                     # Industrials
    "NEE", "PLD",                    # Utilities and Real Estate
]
BENCHMARK = "SPY"

# Waiting list. A bench stock is only bought after passing the free filter + full analysis.
BENCH = [
    "AVGO", "AMD", "CRM", "ORCL", "ADBE",   # Technology
    "NFLX", "DIS",                          # Communication
    "HD", "WMT", "KO", "PEP", "MCD",        # Consumer
    "MA", "BAC",                            # Financials
    "ABBV", "MRK",                          # Healthcare
    "COP",                                  # Energy
    "HON", "UNP",                           # Industrials
    "DUK", "AMT",                           # Utilities and Real Estate
]

# ---------------- RISK LIMITS (Risk agent) ----------------
MAX_POSITION_WEIGHT = 0.10   # no stock over 10% of the portfolio
MIN_CASH_WEIGHT = 0.05       # always keep 5% cash
MAX_SECTOR_WEIGHT = 0.30     # no sector over 30%
MIN_CONFIDENCE = 6           # PM confidence needed to buy
HIGH_VOLATILITY = 0.50       # above this, halve the buy
MAX_DRAWDOWN = 0.10          # portfolio down 10% from peak = no new buys

# ---------------- RULE SWITCHES ----------------
# enabled = rule runs at all. practice = rule only LOGS what it would do (no real trade).
# Leave practice=True for about a week per rule, review data/trades.csv, then set False.
RULES = {
    "stop":      {"enabled": True, "practice": False},
    "news_sell": {"enabled": True, "practice": False},
    "rebalance": {"enabled": True, "practice": False},
    "bench":     {"enabled": True, "practice": False},
}
MAX_RULE_TRADES_PER_DAY = 4  # cap on rule-based trades (stop, news, rebalance)

# ---------------- STOP ----------------
MAX_LOSS_PCT = 0.10          # never lose more than 10% from the buy price
BREAKEVEN_AT = 0.10          # once up 10%, never sell below the buy price
TRAIL_PCT = 0.20             # sell if it falls 20% from its peak
STOP_VOL_REF = 0.30          # stocks more volatile than this get wider stops (sized per stock)
MAX_LOSS_CAP = 0.15          # widest allowed max-loss after sizing
TRAIL_CAP = 0.35             # widest allowed trailing stop after sizing
STOP_CONFIRM_CHECKS = 2      # must be below the stop on 2 checks in a row

# ---------------- REBALANCE ----------------
REBALANCE_ABOVE = 0.12       # trim any stock above 12% ...
REBALANCE_TO = 0.10          # ... back down to 10%

# ---------------- MARKET MODE (strong market = looser rules) ----------------
STRONG_VIX_BELOW = 20        # strong market = SPY above its 200-day average AND VIX under 20
TRAIL_PCT_STRONG = 0.25
REBALANCE_ABOVE_STRONG = 0.15

# ---------------- COOLDOWN + EARNINGS ----------------
COOLDOWN_DAYS = 5            # no rebuy for 5 days after a rule sells a stock
EARNINGS_BLOCK_DAYS = 2      # no new buys within 2 days before earnings

# ---------------- NEWS SELL-HALF ----------------
NEWS_CRITICAL_SCORE = 2      # News agent score must be 2 or below ...
NEWS_MAJOR_OUTLETS = 2       # ... AND (serious 8-K OR 2+ major outlets reporting it)
NEWS_CONFIRM_MINUTES = 30    # only sell if the price is still lower 30 min after the alert
NEWS_GAP_PCT = 0.05          # stock already gapped down 5%+ at the open -> don't auto-sell, ask the PM
NEWS_MIN_MINUTES_BETWEEN_RUNS = 60   # max 1 News agent run per stock per hour
NEWS_KEYWORDS = [
    "investigation", "investigate", "probe", "lawsuit", "sued", "fraud", "recall", "resign",
    "steps down", "fired", "ousted", "sec ", "subpoena", "bankrupt", "downgrade", "scandal",
    "restate", "restatement", "indict", "charged", "guidance cut", "cuts guidance", "warning",
    "breach", "hack", "halt", "ban", "sanction", "spy", "default", "delist",
]
MAJOR_OUTLETS = [
    "reuters", "bloomberg", "wall street journal", "wsj", "cnbc", "financial times",
    "associated press", "new york times", "barron", "marketwatch", "yahoo",
]
SERIOUS_8K_ITEMS = ["1.03", "2.06", "3.01", "4.01", "4.02", "5.02"]

# ---------------- PRICE GUARD + ALERT RUNS ----------------
PRICE_GUARD_MINUTES = 15     # how often the price guard checks
MAX_ALERT_RUNS_PER_DAY = 3   # max extra full-pipeline runs per day triggered by news
NEWS_DROP_TRIGGER = 3        # news score fell 3+ points -> full pipeline review

# ---------------- BENCH ----------------
BENCH_MAX_FULL_CHECKS = 3    # max full analyses per day from the bench (one at a time)
BENCH_MAX_RSI = 75           # skip overheated stocks
BENCH_MIN_FREE_CASH = 0.03   # only run the bench if cash is 3%+ above the minimum cash level

# ---------------- RUN SETTINGS ----------------
RESEARCH_WORKERS = 3         # stocks researched at the same time
AGENT_FAIL_ALERT = 0.5       # alert if 50%+ of research agents fail (e.g. OpenAI out of credit)