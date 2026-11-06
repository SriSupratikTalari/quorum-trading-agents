"""
bull_agent.py
Makes the strongest HONEST case for buying a stock, using only the 4 research reports.
No tools: it reads and argues. The Portfolio Manager makes the decision.
"""
import json
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()
MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are the Bull agent in Quorum, a multi-agent trading system.

You receive 4 research reports on the same stock, written by 4 analyst agents:
fundamentals, technical, news, and macro.

Your job: make the strongest HONEST case for buying this stock.

Rules:
1. Argue for buying, but stay honest. If the bull case is weak, say so and give low conviction.
2. Conviction is 1-10: 1 = almost no reason to buy, 10 = overwhelming evidence.
3. Use ONLY facts from the reports. Never invent numbers, events, or outside information.
4. Every argument must cite the report it came from.
   When a report has `key_metrics`, use those exact numbers in your arguments (e.g. "net margin 24%").
5. Acknowledge the biggest weaknesses in the bull case.
6. Catalysts are upcoming events that could push the price up. Leave the list empty if the reports mention none.

Respond in JSON matching the required schema."""

BULL_SCHEMA = {
    "type": "object",
    "properties": {
        "conviction": {"type": "integer", "description": "1-10 strength of the bull case"},
        "thesis": {"type": "string", "description": "One-sentence bull thesis"},
        "arguments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "source": {"type": "string", "enum": ["fundamentals", "technical", "news", "macro"]},
                },
                "required": ["point", "source"],
                "additionalProperties": False,
            },
        },
        "weaknesses_acknowledged": {"type": "array", "items": {"type": "string"}},
        "catalysts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["conviction", "thesis", "arguments", "weaknesses_acknowledged", "catalysts"],
    "additionalProperties": False,
}


def call_llm(msg: str) -> str:
    resp = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=msg,
        text={"format": {"type": "json_schema", "name": "bull_report", "schema": BULL_SCHEMA, "strict": True}},
    )
    return resp.output_text


def _clean_reports(research: dict) -> dict:
    """Drop raw `data` from each report: Bull needs conclusions, not raw numbers (saves tokens)."""
    return {name: {k: v for k, v in report.items() if k != "data"} for name, report in research.items()}


def run(ticker: str, research: dict) -> dict:
    ticker = ticker.upper()
    msg = f"Ticker: {ticker}\n\nResearch reports:\n{json.dumps(_clean_reports(research), indent=2)}"
    out = call_llm(msg)
    try:
        return {"agent": "bull", "ticker": ticker, **json.loads(out)}
    except json.JSONDecodeError:
        return {"agent": "bull", "ticker": ticker, "error": "invalid JSON", "raw": out}


if __name__ == "__main__":
    # Test without rerunning the research layer: save one research run to this file first.
    sample = Path(__file__).resolve().parents[1] / "data" / "sample_research_AAPL.json"
    research = json.loads(sample.read_text())
    print(json.dumps(run("AAPL", research), indent=2))