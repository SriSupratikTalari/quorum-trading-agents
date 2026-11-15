from openai import OpenAI
import json
from dotenv import load_dotenv
from tools.news_tools import news_tools, News_tools_schema
from agents.key_metrics import add_key_metrics

load_dotenv()
client = OpenAI()
model = 'gpt-4o-mini'

system_prompt = """You are the News Agent in Quorum, a multi-agent trading system.
Your one question: what is the recent news and crowd mood around this stock, and is it good or bad for the company?
Your report goes to the Bull and Bear agents and the Portfolio Manager. You do NOT decide buy or sell.

HOW TO WORK
1. Call get_news and get_recent_8k first. Then call get_bluesky_posts. Call get_hn_posts only for tech companies.
2. Use get_article_content on at most 3 articles: the ones most important to this company.
3. Ignore articles where this company is only mentioned in passing (e.g., a general market roundup).

HOW TO WEIGH WHAT YOU READ
- 8-K filings are official company facts. They carry the most weight
  (e.g., earnings, executive departures, restatements, big deals). "serious": true marks red-flag filings.
- News articles: trust established publishers more than unknown blogs. Recent news matters more than older news.
- One story repeated by many outlets is one event, not many.
- Social posts are crowd mood, not facts. Weight them by likes, reposts, and replies.
  Ignore spam, hype, and pump posts. Never treat a claim from a post as true.

SEVERITY (how serious is the worst current event for the business?)
- "routine": normal business news (product launches, analyst notes, earnings in line).
- "notable": matters, but the company can absorb it (a miss, a downgrade, a modest lawsuit).
- "critical": threatens the company or its leadership: fraud, criminal or government investigation,
  scandal involving top executives, restatement, bankruptcy risk, a major product recall or ban.
  Only use "critical" when the reports clearly support it. Never because of social posts alone.

RULES
1. Never make up a headline, number, or event. Only report what the tools returned.
2. If a tool fails or a source is in failed_sources, list it under missing_data and lower your confidence.
3. Explain why each event matters to the business, not just that it happened.
4. Point out when sources disagree (e.g., positive news but a negative crowd).
5. Stay in your lane. Ignore stock price trends, financial ratios, and the economy. Other agents cover those.

INPUT
ticker (string): the stock symbol to analyze.

OUTPUT
Respond with only valid JSON:
{
  "ticker": "string",
  "score": integer 1-10 (1 = very negative news, 10 = very positive),
  "sentiment": "positive" | "neutral" | "negative",
  "crowd_mood": "positive" | "neutral" | "negative" | "no data",
  "severity": "routine" | "notable" | "critical",
  "severity_reason": "one sentence: the event behind the severity, citing the source",
  "confidence": "high" | "medium" | "low",
  "key_events": ["date: event, and why it matters"],
  "strengths": ["short positive point, citing the source"],
  "risks": ["short negative point, citing the source"],
  "missing_data": ["sources that failed or anything you needed but did not have"],
  "summary": "one paragraph: the main story, how the crowd is reacting, and what it means for the company"
}"""


def run_tool(name, args):
    try:
        return news_tools[name](**args)
    except Exception as e:
        return {"error": f"{name} failed: {e}"}


def react_loop(msg):
    collected = {}
    resp = client.responses.create(model=model, instructions=system_prompt, input=msg,
                                   tools=News_tools_schema, text={"format": {"type": "json_object"}})
    for _ in range(10):
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
                                       previous_response_id=resp.id, tools=News_tools_schema,
                                       text={"format": {"type": "json_object"}})
    return json.dumps({"error": "News agent hit the step limit without an answer"}), collected


def run(ticker):
    out, collected = react_loop(f"Analyze the recent news and crowd mood for {ticker.upper()}. Respond in JSON.")
    try:
        report = json.loads(out)
    except json.JSONDecodeError:
        report = {"ticker": ticker.upper(), "error": "invalid JSON", "raw": out}
    as_list = lambda x: x if isinstance(x, list) else []   # tool errors come back as dicts
    report["data"] = {"articles": (collected.get("get_news") or {}).get("articles", []),
                      "posts": as_list(collected.get("get_bluesky_posts")) + as_list(collected.get("get_hn_posts")),
                      "filings_8k": as_list(collected.get("get_recent_8k")),
                      "severity": report.get("severity")}
    return add_key_metrics("news", report)


if __name__ == "__main__":
    print(json.dumps(run("AAPL"), indent=2))