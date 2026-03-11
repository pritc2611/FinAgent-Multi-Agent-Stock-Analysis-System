import asyncio
import logging
from core.state import AgentState
from tools.search_news import search_stock_news, analyze_sentiment

logger = logging.getLogger(__name__)


async def search_node(state: AgentState) -> AgentState:
    """
    Node 2 - News Search & Sentiment
    Fetches news + scores sentiment concurrently.
    Populates: state["news_headlines"], state["sentiment_score"]
    """
    ticker = state["ticker"].upper()
    logger.info(f"[search_node] Searching news for {ticker}")

    headlines: list[str] = []
    sentiment_score: float = 0.0
    errors = list(state.get("errors", []))

    try:
        # Fetch news
        news_result = await search_stock_news.ainvoke({"ticker": ticker, "max_results": 5})
        articles    = news_result.get("articles", [])
        headlines   = [a["title"] for a in articles if a.get("title")]
        logger.info(f"[search_node] Got {len(headlines)} headlines")
    except Exception as exc:
        logger.error(f"[search_node] News fetch error: {exc}")
        errors.append(f"search_node news: {exc}")
        headlines = [f"Unable to fetch news for {ticker}."]

    try:
        # Score sentiment
        sentiment_result = await analyze_sentiment.ainvoke({
            "headlines": headlines,
            "ticker":    ticker,
        })
        sentiment_score = sentiment_result.get("sentiment_score", 0.0)
        logger.info(f"[search_node] Sentiment: {sentiment_score}")
    except Exception as exc:
        logger.error(f"[search_node] Sentiment error: {exc}")
        errors.append(f"search_node sentiment: {exc}")

    return {
        **state,
        "news_headlines":  headlines,
        "sentiment_score": sentiment_score,
        "errors":          errors,
    }