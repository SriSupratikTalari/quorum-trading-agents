import os
import json
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from tools.fundamentals_tools import fundemental_tools, Fundemental_tools_schema, get_latest_filing_ids
from agents.key_metrics import add_key_metrics

load_dotenv()
client = OpenAI()
model = os.getenv("FUNDAMENTALS_MODEL", "gpt-5-nano")
MAX_DOC_TOKENS = 150_000  # per filing. Fits most full 10-Ks; still caps unusually huge ones
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"

system_prompt = """You are the Fundamentals Agent in Quorum, a multi-agent trading system.
Your one question: is this company a healthy business, and is it improving?
Your report goes to the Bull and Bear agents and the Portfolio Manager. You do NOT decide buy or sell.

HOW TO WORK
1. Call get_fundamentals first.
2. Then ALWAYS call get_10k_document and get_10q_document before answering.
   Use them to explain WHY the numbers look the way they do
   (e.g., what drove growth, why ROE is so high, what management says the main risks are).
3. Your risks must come from the filings' own discussion, not general knowledge.

RULES
1. Take ALL figures from get_fundamentals. Use the filings ONLY to explain why the numbers look the way they do.
   Never pull numbers out of the filing text, because they are easy to misread.
2. Do not do math yourself. Use the ratios provided. If a ratio you need is missing, say so.
3. Never guess. If a tool fails, returns an error, or a document is marked truncated, list it under
   missing_data and lower your confidence.
4. Judge trends across several years and quarters, not one period.
5. Check four areas:
   - Growth: revenue and net income
   - Profitability: margins and ROE
   - Balance sheet: debt-to-equity, current ratio, and cash
   - Cash generation: free cash flow
6. Stay in your lane. Ignore stock price, valuation, news, and the economy. Other agents cover those.

OUTPUT
Respond with only valid JSON:
{
  "ticker": "string",
  "score": integer 1-10 (1 = very weak business, 10 = very strong),
  "verdict": "healthy" | "mixed" | "weak",
  "trend": "improving" | "stable" | "declining",
  "confidence": "high" | "medium" | "low",
  "strengths": ["short point citing the number or filing reason behind it"],
  "risks": ["short point citing the number or filing reason behind it"],
  "missing_data": ["anything you needed but did not have"],
  "summary": "one paragraph: what the numbers show and why, from the filings"
}"""


def run_tool(name, args):
    try:
        result = fundemental_tools[name](**args)
    except Exception as e:
        return {"error": f"{name} failed: {e}"}
    if result is None:
        return {"error": f"{name} found no filing"}
    # Full filings can be huge: cut them so the request doesn't blow the context window
    if isinstance(result, dict) and result.get("approx_tokens", 0) > MAX_DOC_TOKENS:
        result = {**result, "text": result["text"][:MAX_DOC_TOKENS * 4], "truncated": True}
    return result


def react_loop(msg):
    collected = {}
    resp = client.responses.create(model=model, instructions=system_prompt, input=msg,
                                   tools=Fundemental_tools_schema, text={"format": {"type": "json_object"}})
    for _ in range(8):
        calls = [i for i in resp.output if i.type == 'function_call']
        if not calls:
            return resp.output_text, collected
        tools_output = []
        for i in calls:
            result = run_tool(i.name, json.loads(i.arguments))
            collected[i.name] = result
            tools_output.append({'type': 'function_call_output', 'call_id': i.call_id,
                                 'output': json.dumps(result, default=str)})
        resp = client.responses.create(model=model, instructions=system_prompt, input=tools_output,
                                       previous_response_id=resp.id, tools=Fundemental_tools_schema,
                                       text={"format": {"type": "json_object"}})
    return json.dumps({"error": "Fundamentals agent hit the step limit without an answer"}), collected


def run(ticker):
    """What the orchestrator calls. Reuses the saved report until a new 10-K or 10-Q is filed."""
    ticker = ticker.upper()
    path = CACHE_DIR / f"fundamentals_{ticker}.json"
    try:
        ids = get_latest_filing_ids(ticker)
    except Exception:
        ids = None   # can't check -> run fresh

    if ids and path.exists():
        cached = json.loads(path.read_text())
        if cached.get("filing_ids") == ids:
            return {**cached["report"], "cached": True, "cached_at": cached.get("saved_at")}

    out, collected = react_loop(f"Analyze the fundamentals of {ticker}. Respond in JSON.")
    try:
        report = json.loads(out)
    except json.JSONDecodeError:
        report = {"ticker": ticker, "error": "invalid JSON", "raw": out}
    report["data"] = collected.get("get_fundamentals", {})  # not the filing text: it's huge
    report = add_key_metrics("fundamentals", report)

    # Only cache good reports, so a failed run is retried tomorrow
    if ids and "error" not in report:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"filing_ids": ids, "saved_at": datetime.now().isoformat(timespec="seconds"),
                                    "report": report}, default=str))
    return report


if __name__ == "__main__":
    print(json.dumps(run("AAPL"), indent=2))