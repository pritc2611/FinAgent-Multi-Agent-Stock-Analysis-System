import logging
from core.state import AgentState
from core.LLMS import get_llm
from tools.search_news import search_hedging_strategies

logger = logging.getLogger(__name__)


async def risk_mitigation_node(state: AgentState) -> AgentState:
    """
    Node 4 (conditional) – Risk Mitigation
    Researches and summarises hedging strategies for a high-risk position.
    Populates: state["hedging_strategies"]
    """
    ticker = state["ticker"].upper()
    logger.info(f"[risk_mitigation_node] Researching hedging strategies for {ticker}")

    errors = list(state.get("errors", []))
    hedging_strategies = ""

    try:
        # Fetch raw hedge search results
        search_result = await search_hedging_strategies.ainvoke({"ticker": ticker})
        snippets      = search_result.get("snippets", [])
        context       = "\n\n".join(snippets) if snippets else "No search results available."

        # No bind_tools — we need plain text output, not tool invocations
        llm = get_llm()

        system = (
            "You are a derivatives and risk-management specialist. "
            "Synthesise concrete, actionable hedging strategies based on the "
            "research provided. Keep your response focused and practical. "
            "Do not call any tools — write your answer directly."
        )

        user_msg = (
            f"The analyst flagged {ticker} as HIGH RISK.\n\n"
            f"Financial context:\n"
            f"• Price:     ${state.get('financial_data', {}).get('price', 'N/A')}\n"
            f"• P/E:       {state.get('financial_data', {}).get('pe_ratio', 'N/A')}\n"
            f"• Sentiment: {state.get('sentiment_score', 0):.2f}\n"
            f"• Rationale: {state.get('analyst_rationale', '')}\n\n"
            f"Research snippets:\n{context}\n\n"
            "Provide exactly 3 numbered, specific hedging strategies an investor "
            "can implement today. Include the specific instruments (puts, ETFs, stop-losses, etc.)."
        )

        response = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ])

        hedging_strategies = _extract_text(response)

        if not hedging_strategies:
            raise ValueError("LLM returned empty hedging strategies")

        logger.info("[risk_mitigation_node] ✓ Strategies compiled")

    except Exception as exc:
        logger.error(f"[risk_mitigation_node] Error: {exc}")
        errors.append(f"risk_mitigation_node: {exc}")
        hedging_strategies = (
            "1. Purchase protective put options 5-10% out-of-the-money with 60-90 day expiry.\n"
            "2. Reduce position size to 2-3% of portfolio to limit total exposure.\n"
            "3. Set a strict stop-loss order 6-8% below your entry price."
        )

    return {
        **state,
        "hedging_strategies": hedging_strategies,
        "errors":             errors,
    }


def _extract_text(response) -> str:
    """Safely extract plain text from a LangChain AIMessage."""
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            b if isinstance(b, str) else b.get("text", "")
            for b in content
            if isinstance(b, (str, dict))
            and (isinstance(b, str) or b.get("type") == "text")
        ]
        return "\n".join(parts).strip()
    return ""
