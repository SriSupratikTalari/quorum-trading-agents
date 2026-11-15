# Quorum rules upgrade

Added ON TOP of the original pipeline (research -> Bull/Bear -> PM -> Risk -> Execution).

## Safety
- `TRADING_ENABLED` (in `.env`): emergency off switch for all orders.
- Practice mode per rule (`config.RULES`): logs "would do" to `data/trades.csv`, no real trade. Run ~1 week per rule.
- Max 4 rule trades a day. Alert when 50%+ of research agents fail (e.g. OpenAI out of credit).
- Tests: `python -m pytest tests -q`.

## Sell rules (plain Python)
- **Stop**: 10% max loss, breakeven once up 10%, 20% trailing from peak. Wider for jumpy stocks. 2 checks in a row.
- **News sell-half**: critical news (LLM score <= 2 + "critical" AND serious 8-K or 2+ major outlets),
  in profit, price still lower 30 min later -> sell half. Gapped down 5%+ or at a loss -> PM decides.
- **Rebalance**: trim above 12% back to 10%.
- **Market mode**: SPY above 200-day and VIX < 20 -> 25% trailing, 15% rebalance.

## Buy rules
- **Cooldown**: no rebuy for 5 days after any rule sale. PM sees recent rule trades.
- **Earnings block**: no new buys within 2 days before earnings.
- **Bench**: waiting list. Fully sold stocks go to the bench. When cash is freed, once a day:
  cooled-down sold stocks first, then best quick score; free filter; full analysis one at a time.

## Cost savers
- Fundamentals report cached until a new 10-K/10-Q. Macro data cached daily.
- Price guard: free headline check + keyword filter before the News agent, max once per stock per hour.

## Files
New: state.py, alerts.py, rules.py, price_guard.py, bench.py, report.py, tools/cache_utils.py,
tools/valuation_tools.py, tests/test_rules.py. Retired: watcher.py.