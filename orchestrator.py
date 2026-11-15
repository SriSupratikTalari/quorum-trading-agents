"""
orchestrator.py
HOW one stock gets analyzed and traded.
  research_ticker: 4 research agents + valuation, then Bull and Bear   (safe to run for many stocks at once)
  decide_ticker:   PM -> Risk -> Execution                              (touches money: one stock at a time)
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from agents import fundamentals_agent, technical_agent, news_agent, macro_agent
from agents import bull_agent, bear_agent, portfolio_manager_agent, execution_agent
from agents.risk_agent import risk_check
from tools.valuation_tools import get_valuation
from rules import rule_context

RESEARCH = {"fundamentals": fundamentals_agent.run,
            "technical": technical_agent.run,
            "news": news_agent.run,
            "macro": macro_agent.run}


def run_parallel(funcs: dict, *args) -> dict:
    """Run every function at once. One crashing doesn't stop the others."""
    with ThreadPoolExecutor() as pool:
        futures = {name: pool.submit(fn, *args) for name, fn in funcs.items()}
        out = {}
        for name, f in futures.items():
            try:
                out[name] = f.result(timeout=600)
            except Exception as e:
                out[name] = {"error": f"{name} failed: {e}"}
        return out


def research_ticker(ticker: str) -> dict:
    """Phase 1 + 2: no money involved, so many stocks can run at once."""
    state = {"ticker": ticker, "date": date.today().isoformat()}

    # Phase 1: 4 research agents at once
    state["research"] = run_parallel(RESEARCH, ticker)

    # Valuation numbers (no LLM). If yfinance fails, the others still run
    try:
        state["research"]["valuation"] = {"key_metrics": get_valuation(ticker)}
    except Exception as e:
        state["research"]["valuation"] = {"error": f"valuation failed: {e}"}

    # Phase 2: Bull and Bear at once
    debate = run_parallel({"bull": bull_agent.run, "bear": bear_agent.run}, ticker, state["research"])
    state["bull"], state["bear"] = debate["bull"], debate["bear"]
    return state


def decide_ticker(state: dict, rule: str = "pm", practice: bool = False) -> dict:
    """Phase 3: touches money, so run one stock at a time.
    rule/practice let the bench reuse this with its own label and practice mode."""
    ticker = state["ticker"]
    try:
        state["rule_context"] = rule_context(ticker)
    except Exception as e:
        state["rule_context"] = {"error": str(e)}
    state["decision"] = portfolio_manager_agent.run(ticker, state["research"], state["bull"], state["bear"],
                                                    state["rule_context"])
    state["risk"] = risk_check(state["decision"], state["research"])
    reason = (state["decision"].get("reasoning") or "")[:300]
    state["execution"] = execution_agent.execute(state["risk"], rule=rule, reason=reason, practice=practice)
    return state


def run_ticker(ticker: str) -> dict:
    """Full pipeline for one stock (used by the price guard and the bench)."""
    return decide_ticker(research_ticker(ticker))