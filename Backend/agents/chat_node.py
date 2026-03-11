import json
import re
import logging
from datetime import datetime

from core.state import AgentState
from core.LLMS import get_llm

logger = logging.getLogger(__name__)


# Common ticker aliases so we can fast-path the most obvious cases
# without burning an LLM call
_ALIAS_MAP: dict[str, tuple[str, str]] = {
    "apple":      ("AAPL",  "Apple Inc."),
    "microsoft":  ("MSFT",  "Microsoft Corporation"),
    "google":     ("GOOGL", "Alphabet Inc."),
    "alphabet":   ("GOOGL", "Alphabet Inc."),
    "amazon":     ("AMZN",  "Amazon.com Inc."),
    "meta":       ("META",  "Meta Platforms Inc."),
    "facebook":   ("META",  "Meta Platforms Inc."),
    "tesla":      ("TSLA",  "Tesla Inc."),
    "nvidia":     ("NVDA",  "NVIDIA Corporation"),
    "netflix":    ("NFLX",  "Netflix Inc."),
    "salesforce": ("CRM",   "Salesforce Inc."),
    "coinbase":   ("COIN",  "Coinbase Global Inc."),
    "palantir":   ("PLTR",  "Palantir Technologies Inc."),
    "amd":        ("AMD",   "Advanced Micro Devices Inc."),
    "intel":      ("INTC",  "Intel Corporation"),
    "jpmorgan":   ("JPM",   "JPMorgan Chase & Co."),
    "jp morgan":  ("JPM",   "JPMorgan Chase & Co."),
    "disney":     ("DIS",   "The Walt Disney Company"),
    "walmart":    ("WMT",   "Walmart Inc."),
    "berkshire":  ("BRK-B", "Berkshire Hathaway Inc."),
}


async def chat_node(state: AgentState) -> AgentState:
    """
    Node 0 – Chat Node
    Extracts ticker + company from user_query.
    Sets: state["ticker"], state["company_name"], state["chat_response"]
    """
    query  = (state.get("user_query") or "").strip()
    errors = list(state.get("errors", []))

    logger.info(f"[chat_node] Received query: {query!r}")

    # ── LLM extraction ─────────────────────────────────────────────────
    try:
        llm = get_llm()   # no tools bound — we need clean JSON
        
        system = (
            "You are a financial assistant that extracts stock information from user messages.\n"
            "Given a user message, identify the company or stock they are asking about.\n\n"
            "Respond ONLY with a JSON object — no preamble, no markdown, no explanation:\n"
            '{"ticker": "XXXX", "company_name": "Full Company Name Inc.", '
            '"confidence": "high|medium|low", "acknowledgement": "one friendly sentence"}\n\n'
            "Rules:\n"
            "  • ticker must be the official US , india or any country exchange ticker symbol (e.g. AAPL, not Apple)\n"
            '  • If you cannot determine the ticker, set ticker to "UNKNOWN"\n'
            "  • acknowledgement should be warm, mention the company name and ticker,\n"
            "    and tell the user their analysis is starting"
        )

        response = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user",   "content": f"User message: {query}"},
        ])

        raw = _extract_text(response)
        # Strip any accidental markdown fences
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$",          "", raw).strip()

        # Find the JSON object (model may add commentary before/after)
        match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON in LLM response: {raw!r}")

        parsed       = json.loads(match.group())
        ticker       = str(parsed.get("ticker", "UNKNOWN")).upper().strip()
        company_name = str(parsed.get("company_name", ticker)).strip()
        chat_response = str(parsed.get("acknowledgement", "")).strip()
        confidence   = str(parsed.get("confidence", "low")).lower()

        if ticker == "UNKNOWN" or not ticker:
            raise ValueError(f"Could not identify a ticker in query: {query!r}")

        if not chat_response:
            chat_response = (
                f"Starting analysis of **{company_name} ({ticker})**. "
                "Watch the agents work below ↓"
            )

        logger.info(f"[chat_node] LLM extracted: {ticker} ({company_name}) confidence={confidence}")

    except Exception as exc:
        logger.error(f"[chat_node] Extraction failed: {exc}")
        errors.append(f"chat_node: {exc}")
        # Graceful fallback — ask the user to clarify
        ticker        = "UNKNOWN"
        company_name  = "Unknown"
        chat_response = (
            "I couldn't identify a specific stock from your message. "
            "Could you mention the company name or ticker symbol? "
            "For example: *'Analyse Apple'* or *'Tell me about NVDA'*"
        )

    return _build_state(state, ticker, company_name, chat_response, errors)


# ── Helpers ───────────────────────────────────────────────────────────────

def _build_state(
    state: AgentState,
    ticker: str,
    company_name: str,
    chat_response: str,
    errors: list[str],
) -> AgentState:
    return {
        **state,
        "ticker":        ticker,
        "company_name":  company_name,
        "chat_response": chat_response,
        "errors":        errors,
        "started_at":    state.get("started_at") or datetime.utcnow().isoformat(),
    }


def _extract_text(response) -> str:
    """Safely pull text from a LangChain AIMessage."""
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
