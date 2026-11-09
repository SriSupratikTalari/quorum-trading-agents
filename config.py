# config.py
# All tunable settings in one place.

# ---------------- STOCK UNIVERSE ----------------
# Keep this fixed for the whole 3-month test.
UNIVERSE=[
    # Technology
    "AAPL","MSFT","NVDA",
    # Communication
    "GOOGL","META",
    # Consumer
    "AMZN","TSLA","COST","PG",
    # Financials
    "JPM","V",
    # Healthcare
    "UNH","LLY","JNJ",
    # Energy
    "XOM","CVX",
    # Industrials
    "CAT","GE",
    # Utilities and Real Estate
    "NEE","PLD",
]
BENCHMARK="SPY"

# ---------------- RISK LIMITS ----------------
MAX_POSITION_WEIGHT=0.10  # no stock over 10% of the portfolio
MIN_CASH_WEIGHT=0.05      # always keep 5% cash
MAX_SECTOR_WEIGHT=0.30    # no sector over 30%
MIN_CONFIDENCE=6          # PM confidence needed to buy
HIGH_VOLATILITY=0.50      # above this, halve the buy
MAX_DRAWDOWN=0.10         # down more than 10% from peak = no new buys


# ---------------- WATCHER ----------------
CHECK_EVERY_HOURS=2
NEWS_DROP_TRIGGER=3       # score fell by 3+ points since last check
NEWS_LOW_SCORE=3          # or score is 3 or below
MAX_ALERT_RUNS_PER_DAY=3  # cap on extra pipeline runs per day