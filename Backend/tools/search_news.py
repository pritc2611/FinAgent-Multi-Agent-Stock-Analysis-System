import asyncio
from typing import Optional
from langchain_core.tools import tool

# Support both old package name and new renamed package
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS  # type: ignore[no-redef]


@tool
async def search_stock_news(ticker: str, max_results: int = 5) -> dict:
    """
    Search for the latest news headlines about a stock ticker.
    Returns titles, URLs, and publication dates from DuckDuckGo News.
    Use this when the user wants to know about recent news, events,
    or developments related to a company or stock.

    Args:
        ticker:      Stock symbol (e.g. AAPL)
        max_results: Number of headlines to return (default 5, max 10)
    """
    max_results = min(max_results, 10)

    def _blocking():
        with DDGS() as ddgs:
            raw = list(ddgs.news(f"{ticker} stock news earnings", max_results=max_results))
        return [
            {
                "title":  r.get("title", ""),
                "source": r.get("source", ""),
                "date":   r.get("date", ""),
                "url":    r.get("url", ""),
                "body":   r.get("body", ""),
            }
            for r in raw if r.get("title")
        ]

    loop = asyncio.get_event_loop()
    articles = await loop.run_in_executor(None, _blocking)
    return {"ticker": ticker.upper(), "articles": articles}


@tool
async def search_hedging_strategies(ticker: str) -> dict:
    """
    Search for hedging strategies and risk mitigation techniques for a stock.
    Use this when risk_flag is True or the user asks about protecting
    a position, reducing downside risk, or hedging exposure.

    Args:
        ticker: Stock symbol to find hedging strategies for
    """
    def _blocking():
        with DDGS() as ddgs:
            results = list(ddgs.text(
                f"hedging strategies {ticker} stock options puts protective",
                max_results=4,
            ))
        return [r.get("body", "") for r in results if r.get("body")]

    loop = asyncio.get_event_loop()
    snippets = await loop.run_in_executor(None, _blocking)
    return {"ticker": ticker.upper(), "snippets": snippets[:3]}


@tool
async def search_sector_analysis(sector: str) -> dict:
    """
    Search for macro sector trends and analysis.
    Use when user asks about industry trends, sector performance,
    or competitive landscape for a company.

    Args:
        sector: Industry sector name (e.g. "Technology", "Healthcare")
    """
    def _blocking():
        with DDGS() as ddgs:
            results = list(ddgs.text(
                f"{sector} sector stock market outlook 2025",
                max_results=4,
            ))
        return [{"title": r.get("title",""), "body": r.get("body","")} for r in results]

    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, _blocking)
    return {"sector": sector, "results": items}


@tool
async def analyze_sentiment(headlines: list[str], ticker: str) -> dict:
    """
    Analyze the sentiment of news headlines for a stock using NLP heuristics.
    Returns a score from -1.0 (very bearish) to +1.0 (very bullish)
    and a human-readable label.

    Args:
        headlines: List of news headline strings
        ticker:    Stock ticker for context
    """
    if not headlines:
        return {"sentiment_score": 0.0, "label": "Neutral", "reasoning": "No headlines provided"}

    # Keyword-based heuristic (fast, no LLM call)
    positive_kw = {"surge", "soar", "beat", "record", "growth", "profit", "upgrade",
                   "rally", "strong", "bullish", "outperform", "buy", "gain", "rise",
                   "breakthrough", "deal", "partnership", "exceed", "top"}
    negative_kw = {"fall", "drop", "miss", "loss", "decline", "cut", "downgrade",
                   "bearish", "sell", "risk", "warning", "crash", "layoff", "fraud",
                   "lawsuit", "probe", "concern", "weak", "below", "disappoint"}

    text = " ".join(headlines).lower()
    pos  = sum(1 for w in positive_kw if w in text)
    neg  = sum(1 for w in negative_kw if w in text)
    total = pos + neg

    if total == 0:
        score = 0.0
    else:
        score = round((pos - neg) / total, 3)

    label = (
        "Bullish"  if score >  0.2 else
        "Bearish"  if score < -0.2 else
        "Neutral"
    )

    return {
        "ticker":          ticker.upper(),
        "sentiment_score": score,
        "label":           label,
        "positive_signals": pos,
        "negative_signals": neg,
        "reasoning":       f"Found {pos} positive and {neg} negative signals across {len(headlines)} headlines.",
    }
