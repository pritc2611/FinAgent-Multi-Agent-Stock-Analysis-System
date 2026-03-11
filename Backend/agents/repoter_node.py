import re
import logging
from datetime import datetime
from core.state import AgentState
from core.LLMS import get_llm

logger = logging.getLogger(__name__)


async def reporter_node(state: AgentState) -> AgentState:
    """
    Node 5 (terminal) – Reporter
    Generates a structured Investment Brief from all accumulated state.
    Populates: state["investment_memo"], state["completed_at"]
    """
    ticker = state["ticker"].upper()
    logger.info(f"[reporter_node] Compiling Investment Brief for {ticker}")

    financial_data     = state.get("financial_data") or {}
    headlines          = state.get("news_headlines")  or []
    sentiment_score    = state.get("sentiment_score", 0.0)
    risk_flag          = state.get("risk_flag", False)
    analyst_rationale  = state.get("analyst_rationale", "")
    hedging_strategies = state.get("hedging_strategies") or "N/A – no elevated risk detected."
    errors             = list(state.get("errors", []))

    sentiment_label = (
        "Bullish"  if sentiment_score > 0.1
        else "Bearish"  if sentiment_score < -0.1
        else "Neutral"
    )

    investment_memo = ""

    try:
        # No bind_tools — reporter must write text, not call tools
        llm = get_llm()

        system = (
            "You are a Managing Director of Equity Research writing a client Investment Brief. "
            "Be concise, data-driven, and actionable. Use professional markdown formatting "
            "with ## section headers. Write flowing prose — never use tools."
        )

        user_msg = (
            f"Write a complete Investment Brief for {ticker}.\n\n"
            f"=== DATA PACKAGE ===\n"
            f"Date:            {datetime.utcnow().strftime('%Y-%m-%d')}\n"
            f"Ticker:          {ticker}\n"
            f"Company:         {financial_data.get('company_name', ticker)}\n"
            f"Sector:          {financial_data.get('sector', 'Unknown')}\n"
            f"Current Price:   ${financial_data.get('price', 'N/A')}\n"
            f"52-Week High:    ${financial_data.get('week52_high', 'N/A')}\n"
            f"52-Week Low:     ${financial_data.get('week52_low', 'N/A')}\n"
            f"P/E Ratio:       {financial_data.get('pe_ratio', 'N/A')}\n"
            f"Market Cap:      {financial_data.get('market_cap', 'N/A')}\n"
            f"Sentiment:       {sentiment_score:.2f} ({sentiment_label})\n"
            f"Risk Level:      {'HIGH RISK' if risk_flag else 'STANDARD RISK'}\n"
            f"Analyst View:    {analyst_rationale}\n\n"
            f"Top Headlines:\n" + "\n".join(f"  • {h}" for h in headlines) + "\n\n"
            f"Hedging Strategies (if applicable):\n{hedging_strategies}\n\n"
            "Write the brief with these sections:\n"
            "## 1. Executive Summary\n"
            "## 2. Key Metrics\n"
            "## 3. News & Sentiment Analysis\n"
            "## 4. Risk Assessment\n"
            "## 5. Investment Recommendation\n"
            "## 6. Suggested Next Steps\n\n"
            "*Disclaimer: This brief is for informational purposes only "
            "and does not constitute financial advice.*"
        )

        response = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ])

        investment_memo = _extract_text(response)

        if not investment_memo:
            raise ValueError("LLM returned empty content for investment brief")

        logger.info("[reporter_node] ✓ Brief compiled")

    except Exception as exc:
        logger.error(f"[reporter_node] LLM error: {exc}")
        errors.append(f"reporter_node: {exc}")
        investment_memo = _fallback_brief(ticker, state, sentiment_label)

    return {
        **state,
        "investment_memo": investment_memo,
        "completed_at":    datetime.utcnow().isoformat(),
        "errors":          errors,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_text(response) -> str:
    """
    Safely pull plain text from a LangChain AIMessage regardless of
    whether content is a string or a list of content blocks.
    """
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


def _fallback_brief(ticker: str, state: AgentState, sentiment_label: str) -> str:
    fd = state.get("financial_data") or {}
    return (
        f"# Investment Brief – {ticker}\n"
        f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
        f"## Key Metrics\n"
        f"- Price: ${fd.get('price','N/A')} | P/E: {fd.get('pe_ratio','N/A')}\n"
        f"- 52W High: ${fd.get('week52_high','N/A')} | Low: ${fd.get('week52_low','N/A')}\n"
        f"- Sentiment: {sentiment_label}\n\n"
        f"## Risk\n"
        f"{'HIGH RISK' if state.get('risk_flag') else 'STANDARD RISK'}\n\n"
        f"*Disclaimer: Not financial advice.*"
    )
