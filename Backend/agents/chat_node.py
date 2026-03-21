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


_STOPWORDS = {
    "stock",
    "share",
    "shares",
    "company",
    "from",
    "in",
    "of",
    "for",
    "about",
    "please",
    "analyze",
    "analysis",
    "tell",
    "me",
}

async def chat_node(state: AgentState) -> AgentState:
    """
    Node 0 – Chat Node
    
    Resolve ticker + company from user_query with tool-assisted search.
    """
    query = (state.get("user_query") or "").strip()
    errors = list(state.get("errors", []))

    logger.info(f"[chat_node] Received query: query")

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
                        "Find the exact ticker for stock analysis."
                    ),
                },
            ]
        )
        
        resolved = await _resolve_from_tool_calls(ai_msg, query)
        if not resolved:
            resolved = await _fallback_resolve(query)
                
        ticker, company_name = _parse_resolution(resolved)
    

        chat_response = (
            f"Great — I found **{company_name} ({ticker})**. "
            "Starting your stock analysis now."
        )
        logger.info("[chat_node] Resolved ticker: %s (%s)", ticker, company_name)

    except Exception as exc:
        logger.error(f"[chat_node] Extraction failed: exc")
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

async def _fallback_resolve(query: str) -> dict[str, Any]:
    country_hint = _extract_country_hint(query)
    candidates = [query, _strip_noise_words(query)]
    seen: set[str] = set()
    for candidate in candidates:
        cand = (candidate or "").strip()
        if not cand or cand.lower() in seen:
            continue
        seen.add(cand.lower())
        payload = await resolve_ticker_symbol.ainvoke(
            {"company_query": cand, "country_hint": country_hint}
        )
        if (payload or {}).get("status") == "ok":
            return payload
        if (payload or {}).get("matches"):
            return payload
    
    return {"status": "not_found", "query": query, "matches": []}

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

        return await resolve_ticker_symbol.ainvoke(
            {"company_query": company_query, "country_hint": country_hint}
        )

    return None


def _parse_resolution(payload: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Ticker resolver returned invalid payload")

    selected = payload.get("selected") or {}
    matches = payload.get("matches") or []
    status = (payload.get("status") or "").lower().strip()

    candidate = selected if selected else (matches[0] if matches else None)
    if not candidate:
        raise ValueError(f"No ticker candidates found: {payload}")

    ticker = str(candidate.get("ticker") or "").upper().strip()
    company_name = str(candidate.get("company_name") or ticker).strip()
    confidence = float(candidate.get("confidence") or 0.0)

    if not ticker:
        raise ValueError(f"Ticker missing in resolver payload: {payload}")

    if status == "not_found" or confidence < 0.45:
        raise ValueError(f"Low-confidence ticker resolution: {payload}")

    return ticker, company_name

async def _resolve_from_tool_calls(ai_msg: Any, query: str) -> dict[str, Any] | None:
    tool_calls = getattr(ai_msg, "tool_calls", None) or []
    if not tool_calls:
        return None

    for call in tool_calls:
        name = _safe_tool_field(call, "name")
        if name != resolve_ticker_symbol.name:
            continue

        args = _safe_tool_field(call, "args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"company_query": args}

        if not isinstance(args, dict):
            args = {"company_query": query}

        company_query = str(args.get("company_query") or query).strip()
        country_hint = str(args.get("country_hint") or _extract_country_hint(query)).strip()

        return await resolve_ticker_symbol.ainvoke(
            {"company_query": company_query, "country_hint": country_hint}
        )

    return None


def _safe_tool_field(call: Any, key: str) -> Any:
    if isinstance(call, dict):
        return call.get(key)
    return getattr(call, key, None)


def _parse_resolution(payload: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Ticker resolver returned invalid payload")

    selected = payload.get("selected") or {}
    matches = payload.get("matches") or []
    status = str(payload.get("status") or "").lower().strip()

    candidate = selected if selected else (matches[0] if matches else None)
    if not candidate:
        raise ValueError(f"No ticker candidates found: {payload}")

    ticker = str(candidate.get("ticker") or "").upper().strip()
    company_name = str(candidate.get("company_name") or ticker).strip()
    confidence = float(candidate.get("confidence") or 0.0)

    if not ticker:
        raise ValueError(f"Ticker missing in resolver payload: {payload}")
    if status == "not_found" or confidence < 0.45:
        raise ValueError(f"Low-confidence ticker resolution: {payload}")

    return ticker, company_name


def _extract_country_hint(query: str) -> str:
    q = (query or "").lower()
    if "india" in q or "indian" in q:
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


def _strip_noise_words(query: str) -> str:
    words = re.findall(r"[a-zA-Z0-9\.]+", query or "")
    kept = [w for w in words if w.lower() not in _STOPWORDS]
    return " ".join(kept).strip()