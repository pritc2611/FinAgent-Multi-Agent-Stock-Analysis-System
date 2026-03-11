import json
import re
import logging
from core.state import AgentState
from core.LLMS import get_llm
from tools.analysis import calculate_risk_score, calculate_fair_value_range

logger = logging.getLogger(__name__)


async def analyst_node(state: AgentState) -> AgentState:
    """
    Node 3 – Analyst
    Reviews financial data + sentiment, sets risk_flag + analyst_rationale.

    Mandatory risk rules:
      • P/E > 50        → risk_flag = True
      • sentiment < 0   → risk_flag = True

    Strategy: pre-compute tool results, embed them in the prompt,
    then call LLM with NO tool binding so the response is always plain JSON.
    """
    ticker          = state["ticker"].upper()
    financial_data  = state.get("financial_data") or {}
    sentiment_score = state.get("sentiment_score", 0.0)
    pe_ratio        = financial_data.get("pe_ratio")
    errors          = list(state.get("errors", []))

    logger.info(f"[analyst_node] Running risk assessment for {ticker}")

    # ── 1. Hard rule-based check (fast, always applied) ──────────────────────
    rule_risk = bool(
        (pe_ratio is not None and pe_ratio > 50)
        or
        (sentiment_score is not None and sentiment_score < 0)
    )

    risk_flag         = rule_risk
    analyst_rationale = ""

    # ── 2. Pre-compute tool results (direct Python call, no LLM round-trip) ──
    risk_tool_result  = {}
    value_tool_result = {}
    try:
        risk_tool_result = calculate_risk_score.invoke({
            "pe_ratio":        pe_ratio,
            "sentiment_score": sentiment_score or 0.0,
            "price":           financial_data.get("price"),
            "week52_high":     financial_data.get("week52_high"),
            "week52_low":      financial_data.get("week52_low"),
        })
    except Exception as e:
        logger.warning(f"[analyst_node] calculate_risk_score failed: {e}")

    try:
        value_tool_result = calculate_fair_value_range.invoke({
            "pe_ratio": pe_ratio,
            "price":    financial_data.get("price"),
            "sector":   financial_data.get("sector", "Technology"),
        })
    except Exception as e:
        logger.warning(f"[analyst_node] calculate_fair_value_range failed: {e}")

    # ── 3. LLM call — NO tools bound, always returns plain text JSON ─────────
    try:
        llm = get_llm()   # no bind_tools → guaranteed text response

        system = (
            "You are a senior equity risk analyst at a top-tier investment bank.\n"
            "You are given pre-computed quantitative tool results. "
            "Use them along with your professional judgment to assess risk.\n\n"
            "MANDATORY RULES (override everything else):\n"
            "  RULE 1: If P/E ratio > 50  → risk_flag MUST be true\n"
            "  RULE 2: If sentiment < 0   → risk_flag MUST be true\n\n"
            "Respond ONLY with valid JSON — no preamble, no markdown fences:\n"
            '{"risk_flag": true|false, "rationale": "<2-3 sentences max>"}'
        )

        user_msg = (
            f"Ticker: {ticker}\n"
            f"Price:         ${financial_data.get('price', 'N/A')}\n"
            f"52W High/Low:  ${financial_data.get('week52_high', 'N/A')} / ${financial_data.get('week52_low', 'N/A')}\n"
            f"P/E Ratio:     {pe_ratio}\n"
            f"Sector:        {financial_data.get('sector', 'Unknown')}\n"
            f"Sentiment:     {sentiment_score} (-1=bearish … +1=bullish)\n\n"
            f"Pre-computed Risk Score Tool Result:\n{json.dumps(risk_tool_result, indent=2)}\n\n"
            f"Pre-computed Fair Value Tool Result:\n{json.dumps(value_tool_result, indent=2)}\n\n"
            f"Top Headlines:\n"
            + "\n".join(f"  – {h}" for h in (state.get("news_headlines") or []))
            + "\n\nApply the mandatory rules and return JSON."
        )

        response = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ])

        # ── Robust response parsing ───────────────────────────────────────────
        raw = _extract_text(response)
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$",          "", raw).strip()

        # Find the first {...} block even if the model added commentary
        match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in response: {raw!r}")

        parsed            = json.loads(match.group())
        risk_flag         = bool(parsed.get("risk_flag", rule_risk))
        analyst_rationale = str(parsed.get("rationale", "")).strip()

        # Enforce mandatory rules regardless of LLM output
        if rule_risk:
            risk_flag = True
            if not analyst_rationale:
                analyst_rationale = (
                    f"Rule triggered: P/E={pe_ratio}, sentiment={sentiment_score:.2f}."
                )

        logger.info(f"[analyst_node] risk_flag={risk_flag}  {analyst_rationale}")

    except Exception as exc:
        logger.error(f"[analyst_node] LLM error: {exc} – using rule-based flag")
        errors.append(f"analyst_node: {exc}")
        risk_flag         = rule_risk
        analyst_rationale = (
            f"Rule-based assessment: P/E={pe_ratio}, "
            f"sentiment={sentiment_score:.2f}. "
            f"Risk flag set to {rule_risk}. "
            f"Composite risk score: {risk_tool_result.get('composite_risk_score', 'N/A')}."
        )

    return {
        **state,
        "risk_flag":         risk_flag,
        "analyst_rationale": analyst_rationale,
        "errors":            errors,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_text(response) -> str:
    """
    Safely extract text from a LangChain AIMessage.
    Handles three response shapes:
      1. response.content is a plain string  → return it directly
      2. response.content is a list of blocks → join all text blocks
      3. Anything else                        → return empty string
    """
    content = response.content

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts).strip()

    return ""
