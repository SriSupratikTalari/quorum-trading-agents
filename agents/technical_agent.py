from openai import OpenAI
import json
from dotenv import load_dotenv
from tools.technical_tools import technical_tools, Technical_tools_schema

load_dotenv()
client=OpenAI()
model='gpt-4o-mini'

system_prompt="""You are the Technical Agent in Quorum, a multi-agent trading system.
Your one question: what is the stock's price doing, and is the trend healthy?
Your report goes to the Bull and Bear agents and the Portfolio Manager. You do NOT decide buy or sell.

TOOLS
Call both tools before answering.

HOW TO READ THE SIGNALS
- Trend: price above both averages = uptrend. Price below both = downtrend.
  50-day above the 200-day = long-term uptrend.
- Momentum: RSI above 70 = overbought (may pull back). Below 30 = oversold (may bounce). 40-60 = neutral.
- Relative strength: positive outperformance = beating the market. Negative = lagging it.

RULES
1. Take ALL numbers from the tools. Never make up a number.
2. Never calculate. Comparing two numbers (is the price above the average?) is fine.
3. If a tool fails or a value is missing, list it under missing_data and lower your confidence.
4. Explain how the signals fit together. For example, "uptrend, but RSI 78 means it's stretched" is
   better than "trending up, so good." Point out when signals disagree.
5. Stay in your lane. Ignore company financials, news, and the economy. Other agents cover those.

INPUT
ticker (string): the stock symbol to analyze.

OUTPUT
Respond with only valid JSON:
{
  "ticker": "string",
  "score": integer 1-10 (1 = very weak price action, 10 = very strong),
  "verdict": "bullish" | "neutral" | "bearish",
  "trend": "uptrend" | "sideways" | "downtrend",
  "confidence": "high" | "medium" | "low",
  "strengths": ["short point citing the number behind it"],
  "risks": ["short point citing the number behind it"],
  "missing_data": ["anything you needed but did not have"],
  "summary": "one paragraph: what the trend, momentum, and relative strength show together"
}"""

def run_tool(name,args):
    try:
        return technical_tools[name](**args)
    except Exception as e:
        return {"error":f"{name} failed: {e}"}

def react_loop(msg):
    resp=client.responses.create(model=model,instructions=system_prompt,input=msg,
                                 tools=Technical_tools_schema,text={"format":{"type":"json_object"}})
    for _ in range(8):
        calls=[i for i in resp.output if i.type=='function_call']
        if not calls:
            return resp.output_text
        tools_output=[{'type':'function_call_output',
                       'call_id':i.call_id,
                       'output':json.dumps(run_tool(i.name,json.loads(i.arguments)),default=str)
                      } for i in calls]
        resp=client.responses.create(model=model,instructions=system_prompt,input=tools_output,
                                     previous_response_id=resp.id,tools=Technical_tools_schema,
                                     text={"format":{"type":"json_object"}})
    return json.dumps({"error":"Technical agent hit the step limit without an answer"})

def run(ticker):
    out=react_loop(f"Analyze the price action of {ticker.upper()}.")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"ticker":ticker.upper(),"error":"invalid JSON","raw":out}

if __name__=="__main__":
    print(json.dumps(run("AAPL"),indent=2))