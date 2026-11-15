"""
fundamentals_tools.py
Tools for the Fundamentals agent. Tools only FETCH data; the agent does the thinking.

Tools the agent uses:
  1. get_fundamentals(ticker)   -> numbers + ratios (companyfacts API)
  2. get_10k_document(ticker)   -> full text of the latest 10-K
  3. get_10q_document(ticker)   -> full text of the latest 10-Q
Helper (not an agent tool):
  get_latest_filing_ids(ticker) -> newest 10-K/10-Q IDs, used for the report cache
"""
import os
import re
import json
import time
from datetime import date
from pathlib import Path
from functools import lru_cache

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

HEADERS = {"User-Agent": os.getenv("SEC_USER_AGENT", "Sri Talari your_email@example.com")}
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "filings"  # project_root/data/filings

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
_last_call = 0.0


def _get(url: str) -> requests.Response:
    """GET with the SEC rate limit (max ~10 requests/sec)."""
    global _last_call
    wait = 0.12 - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------------------
# TOOL 1: NUMBERS (companyfacts)
# ---------------------------------------------------------------------------

# Companies use different tag names. Earlier tags win if two report the same period.
TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "total_assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "total_liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
}


@lru_cache(maxsize=1)
def _ticker_map() -> dict:
    """Download the ticker->CIK list ONCE and reuse it."""
    data = _get("https://www.sec.gov/files/company_tickers.json").json()
    return {c["ticker"]: str(c["cik_str"]).zfill(10) for c in data.values()}


def get_cik(ticker: str) -> str:
    """'AAPL' -> '0000320193'. SEC writes BRK.B as BRK-B."""
    cik = _ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        raise ValueError(f"Ticker not found: {ticker}")
    return cik


def get_company_facts(cik: str) -> dict:
    return _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json").json()["facts"]["us-gaap"]


def _extract(facts, tags, form, min_days, max_days, n):
    merged = {}
    for tag in tags:  # check ALL tags, since companies sometimes switch tags over the years
        best = {}
        for row in facts.get(tag, {}).get("units", {}).get("USD", []):
            if row.get("form") != form:
                continue
            # Period items (revenue, income): keep only the right length (skip YTD totals)
            if "start" in row:
                days = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
                if not min_days <= days <= max_days:
                    continue
            # Same period appears in several filings: keep the latest one
            end = row["end"]
            if end not in best or row["filed"] > best[end]["filed"]:
                best[end] = row
        for end, row in best.items():
            merged.setdefault(end, row)  # earlier tag wins
    return {end: merged[end]["val"] for end in sorted(merged)[-n:]}


def get_latest_10k(facts: dict, years: int = 4) -> dict:
    return {name: _extract(facts, tags, "10-K", 350, 380, years) for name, tags in TAGS.items()}


def get_latest_10q(facts: dict, quarters: int = 8) -> dict:
    # 8 quarters so each quarter can be compared to the SAME quarter last year
    return {name: _extract(facts, tags, "10-Q", 80, 100, quarters) for name, tags in TAGS.items()}


def _div(a, b):
    return round(a / b, 4) if a is not None and b not in (None, 0) else None


def _year_ago(ends: list, end: str):
    """Find the period that ended ~1 year before `end`."""
    target = date.fromisoformat(end)
    for e in reversed(ends):
        if 350 <= (target - date.fromisoformat(e)).days <= 380:
            return e
    return None


def compute_ratios(annual: dict, quarterly: dict) -> dict:
    rev = annual.get("revenue", {})
    if not rev:
        return {}
    years = sorted(rev)
    end = years[-1]
    a = lambda k: annual.get(k, {}).get(end)  # every value from the same fiscal year
    prev_rev = rev[years[-2]] if len(years) > 1 else None
    ocf, capex = a("operating_cash_flow"), a("capex")

    qrev = quarterly.get("revenue", {})
    qs = sorted(qrev)
    q_end = qs[-1] if qs else None
    q_ni = quarterly.get("net_income", {}).get(q_end)
    q_prior = _year_ago(qs, q_end) if q_end else None

    return {
        "fiscal_year_end": end,
        "gross_margin": _div(a("gross_profit"), rev[end]),
        "operating_margin": _div(a("operating_income"), rev[end]),
        "net_margin": _div(a("net_income"), rev[end]),
        "revenue_growth_yoy": _div(rev[end] - prev_rev, prev_rev) if prev_rev else None,
        "roe": _div(a("net_income"), a("equity")),
        "debt_to_equity": _div(a("long_term_debt"), a("equity")),
        "current_ratio": _div(a("current_assets"), a("current_liabilities")),
        "free_cash_flow": ocf - capex if ocf is not None and capex is not None else None,
        "latest_quarter_end": q_end,
        "latest_quarter_net_margin": _div(q_ni, qrev.get(q_end)),
        # Same quarter vs last year (avoids seasonality, e.g. holiday quarters)
        "quarter_revenue_growth_yoy": _div(qrev[q_end] - qrev[q_prior], qrev[q_prior]) if q_prior else None,
    }


def get_fundamentals(ticker: str) -> dict:
    cik = get_cik(ticker)
    facts = get_company_facts(cik)
    annual = get_latest_10k(facts)
    quarterly = get_latest_10q(facts)
    return {
        "ticker": ticker.upper(),
        "cik": cik,
        "annual": annual,
        "quarterly": quarterly,
        "ratios": compute_ratios(annual, quarterly),
    }


# ---------------------------------------------------------------------------
# TOOLS 2 & 3: FULL FILING DOCUMENTS (10-K, 10-Q)
# ---------------------------------------------------------------------------

def get_latest_filing(cik: str, form: str):
    """Metadata + URL of the newest filing of this form."""
    recent = _get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()["filings"]["recent"]
    for i, f in enumerate(recent["form"]):  # list is newest first
        if f == form:
            acc = recent["accessionNumber"][i]
            return {
                "form": form,
                "accession": acc,
                "filing_date": recent["filingDate"][i],
                "report_date": recent["reportDate"][i],
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{recent['primaryDocument'][i]}",
            }
    return None


def get_filing_text(url: str) -> str:
    """Download a filing (HTML) and turn it into clean plain text."""
    soup = BeautifulSoup(_get(url).text, "html.parser")
    for tag in soup(["script", "style", "ix:header"]):  # ix:header = hidden XBRL data, not readable text
        tag.decompose()
    text = soup.get_text("\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _get_document(ticker: str, form: str):
    """Full filing text. Cached on disk, so each filing is downloaded only once."""
    cik = get_cik(ticker)
    meta = get_latest_filing(cik, form)
    if not meta:
        return None

    path = CACHE_DIR / f"{ticker.upper()}_{meta['accession']}.json"
    if path.exists():
        return json.loads(path.read_text())

    text = get_filing_text(meta["url"])
    doc = {
        "ticker": ticker.upper(),
        **meta,
        "n_chars": len(text),
        "approx_tokens": len(text) // 4,  # rough estimate so the agent can check size before sending
        "text": text,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    return doc


def get_latest_filing_ids(ticker: str) -> dict:
    """Accession numbers of the newest 10-K and 10-Q (one cheap SEC call).
    If these haven't changed, the Fundamentals agent can reuse its saved report."""
    cik = get_cik(ticker)
    recent = _get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()["filings"]["recent"]
    ids = {}
    for i, f in enumerate(recent["form"]):  # newest first
        if f in ("10-K", "10-Q") and f not in ids:
            ids[f] = recent["accessionNumber"][i]
    return ids


def get_10k_document(ticker: str):
    return _get_document(ticker, "10-K")


def get_10q_document(ticker: str):
    return _get_document(ticker, "10-Q")


Fundemental_tools_schema = [
    {
        "type": "function",
        "name": "get_fundamentals",
        "description": "Get exact financial numbers and ratios (revenue, margins, growth, debt, cash flow) "
                       "from SEC data for the last 4 years and 8 quarters. Use these for ALL figures.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker, e.g. 'AAPL'"}
            },
            "required": ["ticker"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_10k_document",
        "description": "Get the full text of the company's latest annual report (10-K). "
                       "Use for long-term strategy, risks, and management's explanation of results.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker, e.g. 'AAPL'"}
            },
            "required": ["ticker"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_10q_document",
        "description": "Get the full text of the company's latest quarterly report (10-Q). "
                       "Use for recent changes, new risks, and the latest quarter's results.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker, e.g. 'AAPL'"}
            },
            "required": ["ticker"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

fundemental_tools = {
    "get_fundamentals": get_fundamentals,
    "get_10k_document": get_10k_document,
    "get_10q_document": get_10q_document,
}