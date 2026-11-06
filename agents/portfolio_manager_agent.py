"""
portfolio_manager_agent.py
Reads the 4 research reports + the Bull and Bear cases, checks the portfolio with its tools,
and decides: buy, sell, or hold, and the target portfolio weight.
Python (not the LLM) turns that weight into a share count.
"""
import os
import json
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from tools.portfolio_tools import (
    portfolio_manager_tools, portfolio_manager_tools_schema, compute_order_size, MAX_WEIGHT,
)

load_dotenv()
client = OpenAI()
MODEL = os.getenv("PM_MODEL", "gpt-4o-mini")  # use your BEST model here: this is the real decision
MAX_STEPS = 6  # safety cap on tool-calling rounds

SYSTEM_PROMPT = f"""You are the Portfolio Manager in Quorum, a multi-agent trading system.

You receive, for one stock:
- 4 research reports (fundamentals, technical, news, macro), each with key_metrics
- a Bull case (argument for buying) and a Bear case (argument against)

Your job: decide BUY, SELL, or HOLD, and the target portfolio weight for this stock.

Steps:
1. Call get_portfolio_context first, so you know the current position, cash, and weight.
2. Weigh the Bull and Bear cases on the quality of their evidence, not just their conviction numbers.
3. Pick a target_weight between 0 and {MAX_WEIGHT}. 0 means own none.
4. Optionally call compute_order_size to preview your decision in shares. Never compute shares yourself.

Rules:
- BUY means target_weight is above the current weight. SELL means below. HOLD means keep the current weight.
- HOLD is a valid answer. Only act when the evidence is clear.
- Use only facts from the inputs and your tools. Never invent numbers or events.
- Confidence is 1-10.
- Name the factors that decided it and the risks you are accepting.

Respond in JSON matching the required schema."""

PM_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
        "target_weight": {"type": "number", "description": f"0 to {MAX_WEIGHT}"},
        "confidence": {"type": "integer", "description": "1-10"},
        "reasoning": {"type": "string", "description": "2-3 sentences"},
        "deciding_factors": {"type": "array", "items": {"type": "string"}},
        "risks_accepted": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["action", "target_weight", "confidence", "reasoning", "deciding_factors", "risks_accepted"],
    "additionalProperties": False,
}


def _clean_reports(research: dict) -> dict:
    """Drop raw `data`; the PM reads conclusions + key_metrics."""
    return {name: {k: v for k, v in r.items() if k != "data"} for name, r in research.items()}


def agent_loop(msg: str):
    """Call the LLM, run any tools it asks for, repeat until it gives a final answer."""
    inputs = [{"role": "user", "content": msg}]
    trace = []  # log of tool calls, for debugging and the dashboard

    for _ in range(MAX_STEPS):
        resp = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=inputs,
            tools=portfolio_manager_tools_schema,
            text={"format": {"type": "json_schema", "name": "pm_decision", "schema": PM_SCHEMA, "strict": True}},
        )
        inputs += resp.output  # keep the model's turn (including its tool calls) in the history

        calls = [item for item in resp.output if item.type == "function_call"]
        if not calls:
            return resp.output_text, trace  # no tools requested -> final answer

        for call in calls:
            try:
                result = portfolio_manager_tools[call.name](**json.loads(call.arguments))
            except Exception as e:  # a failed tool shouldn't crash the agent; tell the model instead
                result = {"error": str(e)}
            trace.append({"tool": call.name, "args": call.arguments, "result": result})
            inputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})

    raise RuntimeError(f"PM did not finish within {MAX_STEPS} steps")


def run(ticker: str, research: dict, bull: dict, bear: dict) -> dict:
    ticker = ticker.upper()
    msg = (
        f"Ticker: {ticker}\n\n"
        f"Research reports:\n{json.dumps(_clean_reports(research), indent=2)}\n\n"
        f"Bull case:\n{json.dumps(bull, indent=2)}\n\n"
        f"Bear case:\n{json.dumps(bear, indent=2)}"
    )

    try:
        out, trace = agent_loop(msg)
        decision = json.loads(out)
    except Exception as e:
        return {"agent": "pm", "ticker": ticker, "action": "hold", "error": str(e)}  # fail safe = do nothing

    # Python sanity checks: never trust the LLM's numbers blindly
    decision["target_weight"] = max(0.0, min(float(decision["target_weight"]), MAX_WEIGHT))
    order = {"side": "none", "shares": 0} if decision["action"] == "hold" \
        else compute_order_size(ticker, decision["target_weight"])

    if decision["action"] != "hold" and order["side"] not in (decision["action"], "none"):
        # e.g. PM said "buy" but its target is below the current weight
        decision["warning"] = f"action '{decision['action']}' contradicts order side '{order['side']}'"
        order = {"side": "none", "shares": 0}

    return {"agent": "pm", "ticker": ticker, **decision, "order": order, "tool_trace": trace}


if __name__ == "__main__":
    # Test with saved outputs so you don't rerun the whole pipeline
    data = Path(__file__).resolve().parents[1] / "data"
    research = json.loads((data / "sample_research_AAPL.json").read_text())
    bull = json.loads((data / "sample_bull_AAPL.json").read_text())
    bear = json.loads((data / "sample_bear_AAPL.json").read_text())
    print(json.dumps(run("AAPL", research, bull, bear), indent=2, default=str))