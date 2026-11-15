import json
from datetime import date, timedelta

import pytest
import state

@pytest.fixture(autouse=True)
def temp_state(tmp_path, monkeypatch):
    """Point state.py at a temp folder, so tests never touch data/state.json."""
    monkeypatch.setattr(state, "DATA", tmp_path)
    monkeypatch.setattr(state, "STATE_PATH", tmp_path/"state.json")

def test_defaults_when_no_file():
    s = state.load_state()
    for key in ("peaks", "buy_dates", "below_stop", "cooldowns",
                "rule_trades_today", "last_news_run", "bench_order"):
        assert key in s
    assert s["rule_trades_today"]["count"] == 0

def test_save_then_load():
    s = state.load_state()
    s["peaks"]["AAPL"] = 250.0
    s["cooldowns"]["NVDA"] = "2026-11-20"
    state.save_state(s)

    loaded = state.load_state()
    assert loaded["peaks"]["AAPL"] == 250.0
    assert loaded["cooldowns"]["NVDA"] == "2026-11-20"

def test_new_day_resets_count():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    state.STATE_PATH.write_text(json.dumps(
        {"rule_trades_today": {"date": yesterday, "count": 3}}))
    assert state.load_state()["rule_trades_today"]["count"] == 0

def test_same_day_keeps_count():
    s = state.load_state()
    s["rule_trades_today"]["count"] = 2
    state.save_state(s)
    assert state.load_state()["rule_trades_today"]["count"] == 2

def test_missing_keys_filled_in():
    state.STATE_PATH.write_text(json.dumps({"peaks": {"AAPL": 200}}))
    s = state.load_state()
    assert s["peaks"]["AAPL"] == 200
    assert s["bench_order"] == []          # added from defaults