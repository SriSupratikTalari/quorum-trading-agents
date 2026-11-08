from concurrent.futures import ThreadPoolExecutor
from agents import fundamentals_agent,technical_agent,news_agent,macro_agent
from agents import bull_agent,bear_agent,portfolio_manager_agent,execution_agent
from agents.risk_agent import risk_check
from config import UNIVERSE

def run_ticker(ticker):
    with ThreadPoolExecutor() as pool:
        # Phase 1: start all 4 at once
        f=pool.submit(fundamentals_agent.run,ticker)
        t=pool.submit(technical_agent.run,ticker)
        n=pool.submit(news_agent.run,ticker)
        m=pool.submit(macro_agent.run,ticker)
        # Wait for all 4 reports
        research={"fundamentals":f.result(),"technical":t.result(),
                  "news":n.result(),"macro":m.result()}

        # Phase 2: Bull and Bear at once
        bull=pool.submit(bull_agent.run,research)
        bear=pool.submit(bear_agent.run,research)
        bull,bear=bull.result(),bear.result()

    # Phase 3: in order
    decision=portfolio_manager_agent.run(ticker,research,bull,bear)
    risk=risk_check(decision,research)
    execution=execution_agent.execute(risk)
    return {"ticker":ticker,"research":research,"bull":bull,"bear":bear,
            "decision":decision,"risk":risk,"execution":execution}

if __name__=="__main__":
    for ticker in UNIVERSE:
        state=run_ticker(ticker)
        print(ticker,state["decision"].get("action"),state["execution"].get("status"))
