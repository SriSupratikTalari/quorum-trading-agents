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
# ---------------- Safety ----------------
TRADING_ENABLED = True            # emergency off switch: False = no trades at all
MAX_RULE_TRADES_PER_DAY = 4       # cap on rule-based trades per day

# ---------------- Rule switches ----------------
# _ON = rule runs at all | _PRACTICE = logs what it would do, no real trade
STOP_ON = True;           STOP_PRACTICE = True
NEWS_SELL_ON = True;      NEWS_SELL_PRACTICE = True
REBALANCE_ON = True;      REBALANCE_PRACTICE = True
MARKET_MODE_ON = True
COOLDOWN_ON = True
EARNINGS_BLOCK_ON = True
BENCH_ON = True;          BENCH_PRACTICE = True

# ---------------- Stop ----------------
STOP_MAX_LOSS = 0.10              # sell if down 10% from buy price
STOP_BREAKEVEN_AT = 0.10          # once up 10%, stop moves to buy price
STOP_TRAILING = 0.20              # then trail 20% below the peak
STOP_CONFIRM_CHECKS = 2           # must be below the stop 2 checks in a row

# ---------------- Rebalance ----------------
REBALANCE_TRIGGER = 0.12          # trim if a position is above 12% of the portfolio
REBALANCE_TARGET = 0.10           # trim back down to 10%

# ---------------- Market mode ----------------
MARKET_SMA_DAYS = 200             # strong market: SPY above its 200-day average
MARKET_VIX_MAX = 20               # and VIX under 20
STRONG_STOP_TRAILING = 0.25       # looser trailing stop in a strong market
STRONG_REBALANCE_TRIGGER = 0.15   # looser trim trigger in a strong market

# ---------------- Buy blocks ----------------
COOLDOWN_DAYS = 5                 # no rebuy for 5 days after any rule sell
EARNINGS_BLOCK_DAYS = 2           # no new buys within 2 days before earnings

# ---------------- Price guard ----------------
PRICE_GUARD_MINUTES = 15          # check prices and headlines every 15 min
NEWS_MIN_MINUTES_BETWEEN = 60     # max 1 News agent run per stock per hour
NEWS_KEYWORDS = ["investigation", "lawsuit", "fraud", "recall",
                 "resigns", "sec", "bankruptcy", "downgrade"]   # lowercase: compare to headline.lower()

# ---------------- Bench ----------------
# filled in at Step 9


