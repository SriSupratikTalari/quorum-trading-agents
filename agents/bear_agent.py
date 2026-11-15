"""
bear_agent.py
Makes the strongest HONEST case AGAINST buying a stock, using only the 4 research reports.
No tools: it reads and argues. The Portfolio Manager makes the decision.
"""
import json
from datetime import date
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()
MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are the Bear agent in Quorum, a multi-agent trading system.

You receive 4 research reports on the same stock (fundamentals, technical, news, macro),
plus valuation numbers (P/E, forward P/E, PEG, analyst target).
Use valuation to judge whether the current price is justified by the business.
Use today's date (given in the message) to tell past events from upcoming ones.

Your job: make the strongest HONEST case against buying this stock (avoid it or sell it).

Rules:
1. Argue against buying, but stay honest. If the bear case is weak, say so and give low conviction.
2. Conviction is 1-10: 1 = almost no reason to avoid it, 10 = overwhelming evidence against it.
3. Use ONLY facts from the reports. Never invent numbers, events, or outside information.
4. Every argument must cite the report it came from.
   When a report has `key_metrics`, use those exact numbers in your arguments (e.g. "net margin 24%").
5. Acknowledge the biggest strengths of the stock that weaken your bear case.
6. Risks are upcoming events or threats that could push the price down. Leave the list empty if the reports mention none.

Respond in JSON matching the required schema."""

BEAR_SCHEMA = {
    "type": "object",
    "properties": {
        "conviction": {"type": "integer", "description": "1-10 strength of the bear case"},
        "thesis": {"type": "string", "description": "One-sentence bear thesis"},
        "arguments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "source": {"type": "string", "enum": ["fundamentals", "technical", "news", "macro", "valuation"]},
                },
                "required": ["point", "source"],
                "additionalProperties": False,
            },
        },
        "strengths_acknowledged": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["conviction", "thesis", "arguments", "strengths_acknowledged", "risks"],
    "additionalProperties": False,
}


def call_llm(msg: str) -> str:
    resp = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=msg,
        text={"format": {"type": "json_schema", "name": "bear_report", "schema": BEAR_SCHEMA, "strict": True}},
    )
    return resp.output_text


def _clean_reports(research: dict) -> dict:
    """Drop raw `data` from each report: Bear needs conclusions, not raw numbers (saves tokens)."""
    return {name: {k: v for k, v in report.items() if k != "data"} for name, report in research.items()}


def run(ticker: str, research: dict) -> dict:
    ticker = ticker.upper()
    msg = f"Today: {date.today().isoformat()}\nTicker: {ticker}\n\nResearch reports:\n{json.dumps(_clean_reports(research), indent=2, default=str)}"
    out = call_llm(msg)
    try:
        return {"agent": "bear", "ticker": ticker, **json.loads(out)}
    except json.JSONDecodeError:
        return {"agent": "bear", "ticker": ticker, "error": "invalid JSON", "raw": out}


if __name__ == "__main__":
    # Test without rerunning the research layer: save one research run to this file first.
    sample = Path(__file__).resolve().parents[1] / "data" / "sample_research_AAPL.json"
    research = json.loads(sample.read_text())
    print(json.dumps(run("AAPL", research), indent=2))