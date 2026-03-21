import asyncio
import re
from typing import Any
from urllib.parse import unquote, urlparse

from langchain_core.tools import tool

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

_COUNTRY_TERMS = {
    "india": ["india", "nse", "bse"],
    "us": ["usa", "us", "nyse", "nasdaq"],
    "uk": ["uk", "lse", "london"],
    "japan": ["japan", "tokyo", "tse"],
    "canada": ["canada", "tsx"],
    "australia": ["australia", "asx"],
    "hong kong": ["hong kong", "hkex"],
}

_TICKER_IN_URL = re.compile(r"/quote/([A-Za-z0-9\-\.\^=]+)")
_TICKER_FALLBACK = re.compile(r"\b([A-Z]{1,6}(?:\.[A-Z]{1,3})?)\b")
_NOISE = {"YAHOO", "FINANCE", "STOCK", "QUOTE", "NSE", "BSE", "NYSE", "NASDAQ", "LSE", "TSE", "TSX", "ASX"}


@tool
async def resolve_ticker_symbol(company_query: str, country_hint: str = "") -> dict:
    """
    Resolve ticker symbol from company name using web search.

    This tool performs web search (DuckDuckGo) and prioritizes
    Yahoo Finance quote URLs to extract an exact ticker.
    """

    def _blocking() -> dict[str, Any]:
        query = (company_query or "").strip()
        if not query:
            return {"status": "not_found", "query": company_query, "matches": []}

        country = (country_hint or "").strip().lower()
        country_terms = _COUNTRY_TERMS.get(country, [])

        search_query = f"{query} yahoo finance ticker"
        if country_terms:
            search_query += " " + " ".join(country_terms[:2])

        candidates: dict[str, dict[str, Any]] = {}

        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=12))

        for item in results:
            title = (item.get("title") or "")
            body = (item.get("body") or "")
            href = (item.get("href") or item.get("url") or "")
            source_text = f"{title} {body}"

            ticker = _extract_ticker_from_url(href) or _extract_ticker_from_text(source_text)
            if not ticker:
                continue

            score = 0.55
            if "finance.yahoo.com" in href:
                score += 0.25
            if country_terms and any(term in source_text.lower() for term in country_terms):
                score += 0.1
            if query.lower() in source_text.lower():
                score += 0.1

            score = min(0.98, round(score, 3))
            prev = candidates.get(ticker)
            if prev and prev["confidence"] >= score:
                continue

            candidates[ticker] = {
                "ticker": ticker,
                "company_name": _clean_company_name(title) or query.title(),
                "exchange": _detect_exchange_from_text(source_text),
                "type": "EQUITY",
                "confidence": score,
                "source_url": href,
            }

        matches = sorted(candidates.values(), key=lambda x: x["confidence"], reverse=True)[:5]
        if not matches:
            return {"status": "not_found", "query": query, "country_hint": country_hint, "matches": []}

        top = matches[0]
        status = "ok" if top["confidence"] >= 0.6 else "ambiguous"

        return {
            "status": status,
            "query": query,
            "country_hint": country_hint,
            "matches": matches,
            "selected": top,
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _blocking)


def _extract_ticker_from_url(url: str) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        path = unquote(parsed.path or "")
        match = _TICKER_IN_URL.search(path)
        if not match:
            return None
        raw = match.group(1).strip().upper()
        raw = raw.split("?")[0].split("/")[0]
        if raw in _NOISE:
            return None
        return raw
    except Exception:
        return None


def _extract_ticker_from_text(text: str) -> str | None:
    for token in _TICKER_FALLBACK.findall((text or "").upper()):
        if token not in _NOISE and len(token) > 1:
            return token
    return None


def _detect_exchange_from_text(text: str) -> str:
    low = (text or "").lower()
    if "nse" in low:
        return "NSE"
    if "bse" in low:
        return "BSE"
    if "nasdaq" in low:
        return "NASDAQ"
    if "nyse" in low:
        return "NYSE"
    if "lse" in low:
        return "LSE"
    return "Web Search"


def _clean_company_name(title: str) -> str:
    clean = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9&.,\- ]", " ", title or "")).strip()
    return clean[:100]
