from openai import OpenAI
from dotenv import load_dotenv
import json
from tools.fundamentals_tools import fundemental_tools, Fundemental_tools_schema

load_dotenv()
client=OpenAI()
model='gpt-4o-mini'
MAX_DOC_TOKENS=50_000  # gpt-4o-mini holds ~128K tokens, and both filings share that space

system_prompt="""You are the Fundamentals Agent in Quorum, a multi-agent trading system.
Your one question: is this company a healthy business, and is it improving?
Your report goes to the Bull and Bear agents and the Portfolio Manager. You do NOT decide buy or sell.

TOOLS
Call get_fundamentals first. Use the filings only to explain the numbers.
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

def run_tool(name,args):
    try:
        result=fundemental_tools[name](**args)
    except Exception as e:
        return {"error":f"{name} failed: {e}"}
    if result is None:
        return {"error":f"{name} found no filing"}
    # Full filings can be huge: cut them so the request doesn't blow the context window
    if isinstance(result,dict) and result.get("approx_tokens",0)>MAX_DOC_TOKENS:
        result={**result,"text":result["text"][:MAX_DOC_TOKENS*4],"truncated":True}
    return result

def react_loop(msg):
    collected={}
    resp=client.responses.create(...)   # unchanged
    for _ in range(8):
        calls=[i for i in resp.output if i.type=='function_call']
        if not calls:
            return resp.output_text,collected
        tools_output=[]
        for i in calls:
            result=run_tool(i.name,json.loads(i.arguments))
            collected[i.name]=result
            tools_output.append({'type':'function_call_output','call_id':i.call_id,
                                 'output':json.dumps(result,default=str)})
        resp=client.responses.create(...)   # unchanged
    return json.dumps({"error":"... hit the step limit without an answer"}),collected

def run(ticker):
    """What the orchestrator calls. Returns a dict."""
    out=react_loop(f"Analyze the fundamentals of {ticker.upper()}.")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"ticker":ticker.upper(),"error":"invalid JSON","raw":out}

if __name__=="__main__":
    print(json.dumps(run("AAPL"),indent=2))

