from concurrent.futures import ThreadPoolExecutor

from agents import fundamentals_agent,technical_agent,news_agent,macro_agent
from agents import bull_agent,bear_agent,portfolio_manager_agent,execution_agent
from agents.risk_agent import risk_check
from datetime import date

RESEARCH={"fundamentals":fundamentals_agent.run,
          "technical":technical_agent.run,
          "news":news_agent.run,
          "macro":macro_agent.run}

def run_parallel(funcs:dict,*args)->dict:
    """Run every function at once. One crashing doesn't stop the others."""
    with ThreadPoolExecutor() as pool:
        futures={name:pool.submit(fn,*args) for name,fn in funcs.items()}
        out={}
        for name,f in futures.items():
            try:
                out[name]=f.result(timeout=300)
            except Exception as e:
                out[name]={"error":f"{name} failed: {e}"}
        return out

def run_ticker(ticker:str)->dict:
    """Run the full pipeline for one stock."""
    state={"ticker":ticker,"date":date.today().isoformat()}

    # Phase 1: 4 research agents at once
    state["research"]=run_parallel(RESEARCH,ticker)

    # Phase 2: Bull and Bear at once
    debate=run_parallel({"bull":bull_agent.run,"bear":bear_agent.run},ticker,state["research"])
    state["bull"],state["bear"]=debate["bull"],debate["bear"]

    # Phase 3: in order
    state["decision"]=portfolio_manager_agent.run(ticker,state["research"],state["bull"],state["bear"])
    state["risk"]=risk_check(state["decision"],state["research"])
    state["execution"]=execution_agent.execute(state["risk"])
    return state