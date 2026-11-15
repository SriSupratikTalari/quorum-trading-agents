"""
report.py
Weekly report (cron: Fridays after the close). Edge vs SPY, trades by rule, win rate,
average win vs average loss. Saved to data/reports/ and sent as an alert.
"""
import csv
from datetime import date, timedelta
from pathlib import Path

from alerts import alert

DATA = Path(__file__).resolve().parent / "data"


def read_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def build_report(days: int = 7) -> str:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    lines = [f"📊 Quorum weekly report ({cutoff} to {date.today().isoformat()})"]

    perf = read_csv(DATA / "performance.csv")
    if len(perf) >= 2:
        start, end = perf[0], perf[-1]
        me = float(end["equity"]) / float(start["equity"]) - 1
        spy = float(end["spy_price"]) / float(start["spy_price"]) - 1
        week = [r for r in perf if r["date"] >= cutoff] or perf[-2:]
        wk_me = float(week[-1]["equity"]) / float(week[0]["equity"]) - 1
        wk_spy = float(week[-1]["spy_price"]) / float(week[0]["spy_price"]) - 1
        lines += [f"Since start ({start['date']}): You {me:+.2%} | SPY {spy:+.2%} | Edge {me - spy:+.2%}",
                  f"This week: You {wk_me:+.2%} | SPY {wk_spy:+.2%} | Edge {wk_me - wk_spy:+.2%}",
                  f"Portfolio value: ${float(end['equity']):,.0f}"]
    else:
        lines.append("Not enough performance data yet.")

    trades = [t for t in read_csv(DATA / "trades.csv") if t["time"][:10] >= cutoff]
    by_rule = {}
    for t in trades:
        key = f"{t['rule']} ({t['status']})"
        by_rule[key] = by_rule.get(key, 0) + 1
    lines.append("Trades by rule: " + (", ".join(f"{k}: {v}" for k, v in sorted(by_rule.items())) or "none"))

    sells = [t for t in trades if t["side"] == "sell" and t["status"] == "filled"
             and t.get("fill_price") and t.get("entry_price")]
    results = [float(t["fill_price"]) / float(t["entry_price"]) - 1 for t in sells]
    if results:
        wins, losses = [r for r in results if r > 0], [r for r in results if r <= 0]
        avg = lambda xs: sum(xs) / len(xs) if xs else 0
        lines.append(f"Closed sells: {len(results)} | win rate {len(wins) / len(results):.0%} | "
                     f"avg win {avg(wins):+.1%} | avg loss {avg(losses):+.1%}")
    practice = [t for t in trades if t["status"] == "practice"]
    if practice:
        lines.append(f"Practice-mode actions to review: {len(practice)} (see data/trades.csv)")
    return "\n".join(lines)


def main():
    text = build_report()
    out = DATA / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{date.today().isoformat()}.md").write_text(text + "\n")
    alert(text)


if __name__ == "__main__":
    main()