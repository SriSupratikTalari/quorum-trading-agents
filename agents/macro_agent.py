from openai import OpenAI
import json
from dotenv import load_dotenv
from tools.marcos_tools import macro_tools, Macro_tools_schema

load_dotenv()
client=OpenAI()
model='gpt-4o-mini'

system_prompt="""You are the Macro Agent in Quorum, a multi-agent trading system.
Your one question: is the economy and overall market a tailwind or a headwind for this stock right now?
Your report goes to the Bull and Bear agents and the Portfolio Manager. You do NOT decide buy or sell.

HOW TO WORK
Call all four tools before answering.

HOW TO READ THE SIGNALS
- Rates: high or rising rates hurt growth stocks (tech) and real estate the most. Falling rates help them.
- Yield curve: inverted (negative) has often come before recessions.
- Inflation: high or rising inflation usually means the Fed keeps rates high.
- Unemployment: rising unemployment means a weakening economy and weaker consumer spending.
- VIX: above 30 = fear in the market. Below 20 = calm.
- Market trend: SPY below its 200-day average = the overall market is weak.
- Sector: a sector beating SPY has wind at its back. One lagging SPY is fighting the market.
- Beta: above 1 = the stock swings more than the market, so it gets hit harder in a downturn.
- Releases: a CPI, jobs, or GDP report in the next few days can move the market sharply.

RULES
1. Take ALL numbers from the tools. Never make up a number.
2. Never calculate. Comparing two numbers is fine.
3. If a tool fails or a value is missing, list it under missing_data and lower your confidence.
4. Connect the economy to THIS stock. Saying "rates are high" is not enough;
   say why that matters for this company's sector and beta.
5. Point out when signals disagree (e.g., strong market but an inverted yield curve).
6. Stay in your lane. Ignore company financials, stock-specific news, and the stock's own chart.
   Other agents cover those.

INPUT
ticker (string): the stock symbol to analyze.

OUTPUT
Respond with only valid JSON:
{
  "ticker": "string",
  "score": integer 1-10 (1 = strong headwind, 10 = strong tailwind),
  "verdict": "tailwind" | "neutral" | "headwind",
  "market_regime": "risk-on" | "mixed" | "risk-off",
  "confidence": "high" | "medium" | "low",
  "strengths": ["short point citing the number behind it"],
  "risks": ["short point citing the number behind it"],
  "upcoming_events": ["date: report name"],
  "missing_data": ["anything you needed but did not have"],
  "summary": "one paragraph: the economic picture and what it means for this stock's sector"
}"""

def run_tool(name,args):
    try:
        return macro_tools[name](**args)
    except Exception as e:
        return {"error":f"{name} failed: {e}"}

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
    out=react_loop(f"Analyze the macro environment for {ticker.upper()}.")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"ticker":ticker.upper(),"error":"invalid JSON","raw":out}

if __name__=="__main__":
    print(json.dumps(run("AAPL"),indent=2))