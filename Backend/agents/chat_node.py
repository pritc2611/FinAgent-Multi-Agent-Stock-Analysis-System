import json
import logging
import re
from datetime import datetime
from typing import Any

from core.LLMS import get_llm
from core.state import AgentState
from tools.ticker_resolver import resolve_ticker_symbol

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "stock", "share", "shares", "company", "from", "in", "of", "for",
    "about", "please", "analyze", "analysis", "tell", "me",
}


async def chat_node(state: AgentState) -> AgentState:
    """Node 0 – resolve ticker + company from the user query."""
    query = (state.get("user_query") or "").strip()
    errors = list(state.get("errors", []))

    logger.info("[chat_node] Received query: %r", query)

    try:
        llm = get_llm(bind_tools=[resolve_ticker_symbol])
        ai_msg = await llm.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract company intent and call resolve_ticker_symbol tool. "
                        "Prefer exact exchange-compatible ticker symbols."
                    ),
                },
                {"role": "user", "content": f"User message: {query}"},
            ]
        )

        resolved = await _resolve_from_tool_calls(ai_msg, query)
        if not resolved:
            resolved = await _fallback_resolve(query)

        ticker, company_name = await _extract_ticker_from_resolver_with_llm(query, resolved)

        chat_response = (
            f"Great — I found **{company_name} ({ticker})**. "
            "Starting your stock analysis now."
        )
        logger.info("[chat_node] Resolved ticker: %s (%s)", ticker, company_name)

    except Exception as exc:
        logger.error("[chat_node] Extraction failed: %s", exc)
        errors.append(f"chat_node: {exc}")
        ticker = "UNKNOWN"
        company_name = "Unknown"
        chat_response = (
            "I couldn't identify an exact stock ticker from your message. "
            "Please share company + country/exchange (example: Reliance India / Apple US)."
        )

    return _build_state(state, ticker, company_name, chat_response, errors)


async def _resolve_from_tool_calls(ai_msg: Any, query: str) -> dict[str, Any] | None:
    tool_calls = getattr(ai_msg, "tool_calls", None) or []
    if not tool_calls:
        return None

    for call in tool_calls:
        name = _safe_field(call, "name")
        if name != resolve_ticker_symbol.name:
            continue

        args = _safe_field(call, "args") or {}
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
        if (payload or {}).get("status") == "ok" or (payload or {}).get("matches"):
            return payload

    return {"status": "not_found", "query": query, "matches": []}


async def _extract_ticker_from_resolver_with_llm(
    query: str,
    resolver_payload: dict[str, Any],
) -> tuple[str, str]:
    """Pass resolver output back to LLM; validate pick against resolver candidates."""
    llm = get_llm()
    prompt = (
        "Select one ticker from resolver output. "
        "Return ONLY JSON: {\"ticker\":\"...\",\"company_name\":\"...\"}. "
        "Ticker must exist in resolver matches."
    )

    try:
        msg = await llm.ainvoke(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"User query: {query}\n"
                        f"Resolver JSON: {json.dumps(resolver_payload, ensure_ascii=False)}"
                    ),
                },
            ]
        )
        raw = _extract_text(msg)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group(0) if match else raw)

        llm_ticker = str(parsed.get("ticker") or "").upper().strip()
        llm_company = str(parsed.get("company_name") or "").strip()

        matches = _resolver_matches(resolver_payload)
        by_symbol = {str(m.get("ticker") or "").upper().strip(): m for m in matches}
        if llm_ticker in by_symbol:
            chosen = by_symbol[llm_ticker]
            return llm_ticker, str(chosen.get("company_name") or llm_company or llm_ticker)
    except Exception:
        pass

    return _parse_resolution(resolver_payload)


def _resolver_matches(payload: dict[str, Any]) -> list[dict[str, Any]]:
    selected = payload.get("selected") or {}
    matches = payload.get("matches") or []
    if selected:
        sel_symbol = str(selected.get("ticker") or "").upper().strip()
        if sel_symbol and all(str(m.get("ticker") or "").upper().strip() != sel_symbol for m in matches):
            matches = [selected, *matches]
    return matches


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


def _safe_field(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _extract_text(msg: Any) -> str:
    content = _safe_field(msg, "content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return "\n".join(parts).strip()
    return ""


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


def _build_state(
    state: AgentState,
    ticker: str,
    company_name: str,
    chat_response: str,
    errors: list[str],
) -> AgentState:
    return {
        **state,
        "ticker": ticker,
        "company_name": company_name,
        "chat_response": chat_response,
        "errors": errors,
        "started_at": state.get("started_at") or datetime.utcnow().isoformat(),
    }
