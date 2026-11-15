"""
Tests for the rule math. Run from the repo root:  python -m pytest tests -q
No API calls: only the pure functions in rules.py and state helpers.
"""
from datetime import date, timedelta

import rules
import state
from config import MAX_RULE_TRADES_PER_DAY

CALM = 0.20     # volatility below STOP_VOL_REF -> normal stop width
JUMPY = 0.60    # twice STOP_VOL_REF -> wider stops


# ---------------- STOP ----------------

def test_stop_max_loss_before_gains():
    assert rules.stop_price(100, 100, CALM) == 90.0          # never lose more than 10%
    assert rules.stop_price(100, 105, CALM) == 90.0          # trailing (84) is lower than max loss


def test_stop_breakeven_lock():
    assert rules.stop_price(100, 110, CALM) == 100.0         # up 10% -> can't sell below the buy price
    assert rules.stop_price(100, 125, CALM) == 100.0


def test_stop_trailing_locks_profit():
    assert rules.stop_price(100, 150, CALM) == 120.0         # 20% below a $150 peak


def test_stop_wider_for_jumpy_stocks():
    assert rules.stop_price(100, 100, JUMPY) == 85.0         # max loss capped at 15%
    assert rules.stop_price(100, 200, JUMPY) == 130.0        # trailing capped at 35%


def test_stop_looser_in_strong_market():
    assert rules.stop_price(100, 200, CALM, strong_market=True) == 150.0   # 25% instead of 20%


def test_stop_needs_two_checks_in_a_row():
    c = rules.next_stop_count(0, 89, 90)
    assert c == 1 and not rules.stop_triggered(c)
    c = rules.next_stop_count(c, 88, 90)
    assert rules.stop_triggered(c)
    assert rules.next_stop_count(1, 91, 90) == 0             # back above the stop -> reset


# ---------------- REBALANCE ----------------

def test_rebalance_trims_back_to_10pct():
    assert rules.rebalance_shares(13_000, 100_000, 100) == 30    # $3K over 10% -> 30 shares
    assert rules.rebalance_shares(11_900, 100_000, 100) == 0     # under 12% -> nothing


def test_rebalance_looser_in_strong_market():
    assert rules.rebalance_shares(14_000, 100_000, 100, strong_market=True) == 0   # limit is 15%


# ---------------- NEWS ----------------

def _report(score, severity, filings=(), articles=()):
    return {"score": score, "severity": severity, "data": {"filings_8k": list(filings), "articles": list(articles)}}


def test_news_needs_two_signals():
    today = date.today().isoformat()
    serious = [{"serious": True, "filing_date": today}]
    assert rules.is_critical_news(_report(2, "critical", filings=serious))[0]
    assert not rules.is_critical_news(_report(2, "critical"))[0]                      # LLM alone isn't enough
    assert not rules.is_critical_news(_report(6, "notable", filings=serious))[0]      # 8-K alone isn't enough


def test_news_major_outlets_count_as_second_signal():
    arts = [{"headline": "Board launches investigation into CEO", "publisher": "Reuters"},
            {"headline": "CEO faces probe", "publisher": "Bloomberg"},
            {"headline": "New phone launch", "publisher": "WSJ"}]   # no red-flag word -> not counted
    assert rules.major_outlet_count(arts) == 2
    assert rules.is_critical_news(_report(1, "critical", articles=arts))[0]


def test_old_8k_does_not_count():
    old = (date.today() - timedelta(days=20)).isoformat()
    assert not rules.is_critical_news(_report(2, "critical", filings=[{"serious": True, "filing_date": old}]))[0]


def test_gap_rule():
    assert rules.gapped_down(94, 100)        # -6% open
    assert not rules.gapped_down(98, 100)    # -2% open
    assert not rules.gapped_down(None, 100)


def test_earnings_block():
    assert rules.earnings_blocks_buy(0) and rules.earnings_blocks_buy(2)
    assert not rules.earnings_blocks_buy(3)
    assert not rules.earnings_blocks_buy(None)


# ---------------- STATE ----------------

def test_cooldown_and_daily_cap():
    s = state._default()
    state.set_cooldown(s, "NVDA")
    assert state.cooldown_until("NVDA", s) is not None
    assert state.cooldown_until("AAPL", s) is None
    for _ in range(MAX_RULE_TRADES_PER_DAY):
        state.add_rule_trade(s, {"date": state.today(), "ticker": "NVDA", "rule": "stop"})
    assert state.rule_trades_today(s) == MAX_RULE_TRADES_PER_DAY


def test_bench_moves():
    s = state._default()
    state.move_to_bench(s, "XOM")
    assert "XOM" not in s["active"] and s["bench"][-1] == "XOM" and "XOM" in s["sold"]
    state.move_to_active(s, "XOM")
    assert "XOM" in s["active"] and "XOM" not in s["bench"] and "XOM" not in s["sold"]