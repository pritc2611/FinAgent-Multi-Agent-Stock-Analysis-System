import json
import logging
import re
from datetime import datetime
from tools.ticker_resolver import resolve_ticker_symbol
from core.state import AgentState
from core.state import AgentState
from core.LLMS import get_llm
from typing import Any

logger = logging.getLogger(__name__)

async def chat_node(state: AgentState) -> AgentState:
    """
    Node 0 – Chat Node
    
    Resolve ticker + company from user_query with tool-assisted search.
    """
    query = (state.get("user_query") or "").strip()
    errors = list(state.get("errors", []))

    logger.info(f"[chat_node] Received query: {query}")

    # ── LLM extraction ─────────────────────────────────────────────────
    try:

        llm = get_llm(bind_tools=[resolve_ticker_symbol])   # no tools bound — we need clean JSON
        
        system = (
            "You are a financial assistant.\n"
            "Step 1: extract the target company name from the user query.\n"
            "Step 2: call resolve_ticker_symbol to get the exact tradable ticker.\n"
            "Do not guess ticker symbols when tool lookup is needed."
        )

        ai_msg = await llm.ainvoke(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"User message: {query}\n"
                    ),
                },
            ]
        )
        logger.info(f"[chat_node] invoked : {ai_msg}")
        
        resolved = await _resolve_from_tool_calls(ai_msg, query)
        logger.info(f"[chat_node] resolved output : {resolved}")
                
        ticker, company_name = await _parse_resolution(resolved)
        logger.info(f"[chat_node] resolved output : {ticker,company_name}")
    

        chat_response = (
            f"Great — I found **{company_name} ({ticker})**. "
            "Starting your stock analysis now."
        )
        logger.info("[chat_node] Resolved ticker: %s (%s)", ticker, company_name)

    except Exception as exc:
        logger.error(f"[chat_node] Extraction failed: {exc}")
        errors.append(f"chat_node: {exc}")
        # Graceful fallback — ask the user to clarify
        ticker        = "UNKNOWN"
        company_name  = "Unknown"
        chat_response = (
            "I couldn't identify an exact stock ticker from your message. "
            "Please share the company name and, if possible, the country/exchange "
            "(example: Reliance India, Toyota Japan, Apple US)."
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
        "ticker":ticker,
        "company_name":company_name,
        "chat_response":chat_response,
        "errors":errors,
        "started_at":state.get("started_at") or datetime.utcnow().isoformat(),
    }


async def _resolve_from_tool_calls(ai_msg: Any, query: str) -> dict[str, Any] | None:
    tool_calls = getattr(ai_msg, "tool_calls", None) or []
    if not tool_calls:
        return None

    for call in tool_calls:
        name = (call.get("name") or "").strip()
        if name != resolve_ticker_symbol.name:
            continue

        args = call.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"company_query": args}

        company_query = (args.get("company_query") or query).strip()
        country_hint = (args.get("country_hint") or "").strip()
        country_hint = _extract_country_hint(query)

        return await resolve_ticker_symbol.ainvoke(
            {"company_query": company_query, "country_hint": country_hint}
        )

    return None


async def _parse_resolution(payload: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Ticker resolver returned invalid payload")

    system = f""""Acting as a extractor, extract the company and ticker symbol mentioned in the user's request. and never ever breake strict rules
                  
    strict rule:- Provide the details in this JSON format:
    {{ "ticker" : "XXXX", "company_name" : "Full Company Name Inc." }}
    
    1. don't call any tools, just extract what you have said
    2. never ever give empty output, you must give the output  
    3. format must be in json, as mentioned                    
    

    User Query: {payload}"""

    llm = get_llm()
    output = await llm.ainvoke(system)

    import re
    import json

    clean_output = json.loads(re.sub(r'```json\n|```', '', output.content).strip())

    ticker = clean_output["ticker"]
    company_name = clean_output["company_name"]                       
    return ticker, company_name


def _extract_country_hint(query: str) -> str:
    q = (query or "").lower()
    if "india" in q or "indian"  in q:
        return "india"
    if "japan" in q:
        return "japan"
    if "uk" in q or "united kingdom" in q:
        return "uk"
    if "canada" in q:
        return "canada"
    if "australia" in q:
        return "australia"
    if "hong kong" in q:
        return "hong kong"
    if "us" in q or "usa" in q or "united states" in q:
        return "us"
    return ""

