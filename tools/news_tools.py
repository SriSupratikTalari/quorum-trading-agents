import os
import re
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from functools import lru_cache
from datetime import date,timedelta,datetime,timezone
from dotenv import load_dotenv
from tools.fundamentals_tools import get_cik,_get  # reuse SEC lookup + rate limit

load_dotenv()
ALPACA_HEADERS={"APCA-API-KEY-ID":os.getenv("ALPACA_API_KEY"),
                "APCA-API-SECRET-KEY":os.getenv("ALPACA_SECRET_KEY")}

def _iso(ts):
    """Unix seconds -> ISO UTC string."""
    return datetime.fromtimestamp(ts,timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _article(source_api,headline,summary,publisher,published_at,url):
    return {"source_api":source_api,"headline":headline,"summary":summary,
            "publisher":publisher,"published_at":published_at,"url":url}

# ---------------- ARTICLES ----------------

def get_alpaca_news(ticker:str,days:int=7)->list:
    start=(date.today()-timedelta(days=days)).isoformat()
    params={'symbols':ticker,'start':start,'limit':50,'sort':'desc'}
    r=requests.get('https://data.alpaca.markets/v1beta1/news',headers=ALPACA_HEADERS,params=params,timeout=15)
    r.raise_for_status()
    return [_article("alpaca",n["headline"],n["summary"],n["source"],n["created_at"],n["url"])
            for n in r.json()["news"]]

def get_yahoo_news(ticker:str,days:int=7)->list:
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out=[]
    for item in yf.Ticker(ticker).news:
        n=item.get("content") or {}
        published=n.get("pubDate","")
        if published<cutoff:
            continue
        out.append(_article("yahoo",n.get("title"),n.get("summary"),
                            (n.get("provider") or {}).get("displayName"),published,
                            (n.get("canonicalUrl") or {}).get("url")))
    return out

def get_finnhub_news(ticker:str,days:int=7)->list:
    params={'symbol':ticker,
            'from':(date.today()-timedelta(days=days)).isoformat(),
            'to':date.today().isoformat()}
    r=requests.get('https://finnhub.io/api/v1/company-news',
                   headers={'X-Finnhub-Token':os.getenv("FINNHUB_API")},params=params,timeout=15)
    r.raise_for_status()
    return [_article("finnhub",n["headline"],n["summary"],n["source"],_iso(n["datetime"]),n["url"])
            for n in r.json()]

def merge_and_dedupe(lists:list)->list:
    """Newest first. Same headline from two sources = one article."""
    seen,out=set(),[]
    for a in sorted([a for l in lists for a in l],key=lambda a:a["published_at"] or "",reverse=True):
        key=re.sub(r"[^a-z0-9]","",(a["headline"] or "").lower())
        if key and key not in seen:
            seen.add(key)
            out.append(a)
    return out

def get_news(ticker:str)->dict:
    """One call for the agent: all 3 sources, merged. One source failing doesn't stop the others."""
    lists,failed=[],[]
    for name,fn in [("alpaca",get_alpaca_news),("yahoo",get_yahoo_news),("finnhub",get_finnhub_news)]:
        try:
            lists.append(fn(ticker))
        except Exception as e:
            failed.append(f"{name}: {e}")
    return {"articles":merge_and_dedupe(lists)[:40],"failed_sources":failed}

JUNK=["something went wrong","not a broker-dealer","edit your dock"]

def get_article_content(url:str)->str:
    r=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15)
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    body=soup.find("div",class_="body-wrap") or soup
    paras=[re.sub(r"\s+"," ",p.get_text()).strip() for p in body.find_all("p")]
    paras=[p for p in paras if len(p)>40 and not any(j in p.lower() for j in JUNK)]
    text="\n\n".join(paras)
    return text[:8000] if text else "No article text found (video, paywall, or blocked)."

# ---------------- FILINGS ----------------

ITEMS_8K={
    "1.01":"New major agreement","1.02":"Major agreement ended","1.03":"Bankruptcy",
    "2.01":"Acquisition or sale completed","2.02":"Earnings results","2.03":"New debt",
    "2.05":"Restructuring or layoffs","2.06":"Asset write-down","3.01":"Delisting notice",
    "4.01":"Auditor change","4.02":"Past financials can't be relied on (restatement)",
    "5.02":"Executive or director change","5.03":"Bylaws change","5.07":"Shareholder vote results",
    "7.01":"Investor disclosure (Reg FD)","8.01":"Other events","9.01":"Financial statements and exhibits",
}

def get_recent_8k(ticker:str,days:int=30)->list:
    cik=get_cik(ticker)
    recent=_get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()["filings"]["recent"]
    cutoff=(date.today()-timedelta(days=days)).isoformat()
    out=[]
    for i,form in enumerate(recent["form"]):
        if form!="8-K" or recent["filingDate"][i]<cutoff:
            continue
        items=[x.strip() for x in recent["items"][i].split(",") if x.strip()]
        acc=recent["accessionNumber"][i]
        out.append({"filing_date":recent["filingDate"][i],
                    "items":items,
                    "item_meanings":[ITEMS_8K.get(x,"Other") for x in items],
                    "url":f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{recent['primaryDocument'][i]}"})
    return out

# ---------------- CROWD MOOD ----------------

@lru_cache(maxsize=1)
def _bsky_token():
    """Log in once per run."""
    r=requests.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                    json={"identifier":os.getenv("BLUESKY_HANDLE"),"password":os.getenv("BLUESKY_APP_PASSWORD")},
                    timeout=15)
    r.raise_for_status()
    return r.json()["accessJwt"]

def get_bluesky_posts(ticker:str,limit:int=50)->list:
    r=requests.get("https://bsky.social/xrpc/app.bsky.feed.searchPosts",
                   headers={"Authorization":f"Bearer {_bsky_token()}"},
                   params={"q":f"${ticker.upper()}","limit":limit,"sort":"latest"},timeout=15)
    r.raise_for_status()
    return [{"platform":"bluesky","text":p["record"].get("text"),"author":p["author"]["handle"],
             "created_at":p["record"].get("createdAt"),"likes":p.get("likeCount",0),
             "reposts":p.get("repostCount",0),"replies":p.get("replyCount",0),
             "url":f"https://bsky.app/profile/{p['author']['handle']}/post/{p['uri'].split('/')[-1]}"}
            for p in r.json()["posts"]]

def get_hn_posts(company_name:str,days:int=7)->list:
    since=int((datetime.now(timezone.utc)-timedelta(days=days)).timestamp())
    r=requests.get("https://hn.algolia.com/api/v1/search_by_date",
                   params={"query":company_name,"tags":"story",
                           "numericFilters":f"created_at_i>{since}","hitsPerPage":30},timeout=15)
    r.raise_for_status()
    return [{"platform":"hackernews","text":h.get("title"),"author":h.get("author"),
             "created_at":_iso(h["created_at_i"]),"likes":h.get("points",0),"reposts":None,
             "replies":h.get("num_comments",0),"url":f"https://news.ycombinator.com/item?id={h['objectID']}"}
            for h in r.json()["hits"]]

# ---------------- SCHEMA ----------------

def _schema(name,desc,param,param_desc):
    return {"type":"function","name":name,"description":desc,
            "parameters":{"type":"object",
                          "properties":{param:{"type":"string","description":param_desc}},
                          "required":[param],"additionalProperties":False},
            "strict":True}

News_tools_schema=[
    _schema("get_news","Recent news articles (last 7 days) about the stock from Alpaca, Yahoo, and Finnhub, "
            "merged with duplicates removed. Each has a headline, summary, publisher, date, and url.",
            "ticker","Stock ticker, e.g. 'AAPL'"),
    _schema("get_article_content","Full text of one article. Use only for the few articles that matter most.",
            "url","The article url from get_news"),
    _schema("get_recent_8k","The company's official SEC 8-K filings from the last 30 days: "
            "material events like earnings, executive changes, deals, or restatements.",
            "ticker","Stock ticker, e.g. 'AAPL'"),
    _schema("get_bluesky_posts","Recent Bluesky posts mentioning the stock's cashtag. Crowd mood, not facts.",
            "ticker","Stock ticker, e.g. 'AAPL'"),
    _schema("get_hn_posts","Recent Hacker News stories about the company (last 7 days). Most useful for tech companies. "
            "Crowd mood, not facts.",
            "company_name","Company name, e.g. 'Apple'"),
]

news_tools={
    "get_news":get_news,
    "get_article_content":get_article_content,
    "get_recent_8k":get_recent_8k,
    "get_bluesky_posts":get_bluesky_posts,
    "get_hn_posts":get_hn_posts,
}

if __name__=="__main__":
    import json
    print(json.dumps(get_news("AAPL")["articles"][:3],indent=2))
    print(json.dumps(get_recent_8k("AAPL"),indent=2))
    print(json.dumps(get_hn_posts("Apple")[:3],indent=2))