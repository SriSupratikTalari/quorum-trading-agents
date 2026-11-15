"""
cache_utils.py
@daily_cache: remember a function's result for the rest of the day (resets at midnight).
Used for data that only changes once a day (economy data, volatility, earnings dates).
"""
import threading
from datetime import date
from functools import wraps


def daily_cache(fn):
    cache, lock = {}, threading.Lock()

    @wraps(fn)
    def wrapper(*args):
        key = (date.today(), args)
        with lock:
            if key in cache:
                return cache[key]
        result = fn(*args)          # errors are NOT cached, so a failed call is retried next time
        with lock:
            for k in [k for k in cache if k[0] != date.today()]:
                del cache[k]        # drop yesterday's entries
            cache[key] = result
        return result

    return wrapper