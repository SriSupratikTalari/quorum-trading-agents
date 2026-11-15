"""
key_metrics.py
Picks the 5-8 most important numbers from each research agent's raw `data`.
Bull, Bear and the PM read `key_metrics` instead of the huge raw `data`.

Usage inside each research agent, right before returning the report:
    from agents.key_metrics import add_key_metrics
    report = add_key_metrics("technical", report)

If your agent's `data` uses different key names, change them in the matching function below.
"""


def _pick(d: dict, keys: list) -> dict:
    """Keep only these keys, skip missing or empty ones."""
    return {k: d[k] for k in keys if isinstance(d, dict) and d.get(k) is not None}


def _round(d: dict, n: int = 4) -> dict:
    """Round floats so the LLM doesn't get 0.2400000001."""
    return {k: round(v, n) if isinstance(v, float) else v for k, v in d.items()}


def fundamentals_metrics(data: dict) -> dict:
    ratios = data.get("ratios", {})
    return _pick(ratios, [
        "fiscal_year_end", "revenue_growth_yoy", "quarter_revenue_growth_yoy",
        "gross_margin", "net_margin", "roe", "debt_to_equity", "free_cash_flow",
    ])


def technical_metrics(data: dict) -> dict:
    ind = data.get("indicators", data)  # works whether indicators are nested or flat
    rs = data.get("relative_strength", {})
    return {
        **_pick(ind, ["price", "above_sma_50", "above_sma_200", "rsi_14",
                      "ret_3m", "pct_from_52w_high", "volatility_20d"]),
        **_pick(rs, ["outperformance"]),
    }


def news_metrics(data: dict) -> dict:
    articles = data.get("articles", [])
    posts = data.get("posts", [])
    filings = data.get("filings_8k", [])
    out = {
        "n_articles": len(articles),
        "n_posts": len(posts),
        "total_post_likes": sum(p.get("likes") or 0 for p in posts),
        "major_8k_events": [m for f in filings for m in f.get("item_meanings", [])],
    }
    # Keep counts the agent already computed (e.g. positive/negative from the LLM)
    out.update(_pick(data, ["n_last_24h", "n_positive", "n_negative", "severity"]))
    out["serious_8k"] = any(f.get("serious") for f in filings)
    return out


def macro_metrics(data: dict) -> dict:
    m = data.get("macro", {})
    sector = data.get("sector") or {}
    latest = lambda k: (m.get(k) or {}).get("latest")
    out = {
        "fed_funds_rate": latest("fed_funds_rate"),
        "ten_year": latest("treasury_10y"),
        "ten_year_change_1y": (m.get("treasury_10y") or {}).get("change_1y"),
        "inflation_pct": m.get("inflation_pct"),
        "unemployment": latest("unemployment_rate"),
        "vix": latest("vix"),
        "yield_curve": latest("yield_curve_10y_2y"),
        "curve_inverted": m.get("yield_curve_inverted"),
        "beta": sector.get("beta"),
        "sector_outperformance": (sector.get("sector_vs_spy_90d") or {}).get("sector_outperformance"),
    }
    return {k: v for k, v in out.items() if v is not None}


EXTRACTORS = {
    "fundamentals": fundamentals_metrics,
    "technical": technical_metrics,
    "news": news_metrics,
    "macro": macro_metrics,
}


def add_key_metrics(agent: str, report: dict) -> dict:
    """Add `key_metrics` to a report. Never crashes the agent: falls back to {}."""
    try:
        report["key_metrics"] = _round(EXTRACTORS[agent](report.get("data", {})))
    except Exception as e:
        report["key_metrics"] = {}
        report["key_metrics_error"] = str(e)
    return report