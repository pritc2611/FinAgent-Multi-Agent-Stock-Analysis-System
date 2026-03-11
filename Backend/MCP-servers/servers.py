import asyncio
import sys
import os

# Ensure backend root is on path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from core.config import settings
from tools import ALL_TOOLS

# ── Instantiate FastMCP server ─────────────────────────────────────────────
mcp = FastMCP(settings.mcp_server_name)


# ── Register every tool from the registry ─────────────────────────────────
# Each tool decorated with @tool becomes an MCP-callable endpoint.
# The LLM uses the tool's docstring to decide WHEN to call it.


@mcp.tool()
async def get_stock_price(ticker: str) -> dict:
    """
    Get the current stock price and key metrics for a ticker.
    Delegates to fetch_market_data tool.
    """
    from tools.curent_market_data import fetch_market_data
    return await fetch_market_data.ainvoke({"ticker": ticker})


@mcp.tool()
async def get_historical_prices(ticker: str, period: str = "3mo") -> dict:
    """
    Get historical OHLCV price data for chart generation or trend analysis.
    period options: 1mo, 3mo, 6mo, 1y, 2y
    """
    from tools.curent_market_data import fetch_historical_prices
    return await fetch_historical_prices.ainvoke({"ticker": ticker, "period": period})


@mcp.tool()
async def compare_multiple_stocks(tickers: list[str]) -> dict:
    """
    Compare key financial metrics across multiple stocks side by side.
    Perfect for competitive analysis.
    """
    from tools.curent_market_data import compare_stocks
    return await compare_stocks.ainvoke({"tickers": tickers})


@mcp.tool()
async def get_stock_news(ticker: str, max_results: int = 5) -> dict:
    """
    Retrieve the latest news headlines for a stock from the web.
    Returns titles, sources, dates, and article bodies.
    """
    from tools.search_news import search_stock_news
    return await search_stock_news.ainvoke({"ticker": ticker, "max_results": max_results})


@mcp.tool()
async def get_hedging_strategies(ticker: str) -> dict:
    """
    Research and return hedging strategies to reduce risk for a stock position.
    Use when the risk_flag is True or user asks about protecting their investment.
    """
    from tools.search_news import search_hedging_strategies
    return await search_hedging_strategies.ainvoke({"ticker": ticker})


@mcp.tool()
async def get_sector_outlook(sector: str) -> dict:
    """
    Get macro-level sector trends and analyst outlooks.
    Use for industry-level analysis alongside stock-specific research.
    """
    from tools.search_news import search_sector_analysis
    return await search_sector_analysis.ainvoke({"sector": sector})


@mcp.tool()
async def score_news_sentiment(headlines: list[str], ticker: str) -> dict:
    """
    Analyze sentiment of a list of news headlines for a stock.
    Returns a score from -1.0 (bearish) to +1.0 (bullish) with explanation.
    """
    from tools.search_news import analyze_sentiment
    return await analyze_sentiment.ainvoke({"headlines": headlines, "ticker": ticker})


@mcp.tool()
async def get_risk_score(
    ticker: str,
    pe_ratio: float | None = None,
    sentiment_score: float = 0.0,
    price: float | None = None,
    week52_high: float | None = None,
    week52_low: float | None = None,
) -> dict:
    """
    Calculate a composite risk score (0–100) for a stock.
    Combines P/E valuation risk, sentiment risk, and price momentum.
    Returns risk level: LOW / MEDIUM / HIGH and a risk_flag boolean.
    """
    from tools.analysis import calculate_risk_score
    return calculate_risk_score.invoke({
        "pe_ratio": pe_ratio,
        "sentiment_score": sentiment_score,
        "price": price,
        "week52_high": week52_high,
        "week52_low": week52_low,
    })


@mcp.tool()
async def get_fair_value(
    ticker: str,
    pe_ratio: float | None = None,
    price: float | None = None,
    sector: str = "Technology",
) -> dict:
    """
    Estimate a fair-value price range using sector-average P/E benchmarks.
    Returns low/mid/high fair value and a verdict (OVERVALUED / FAIRLY_VALUED / UNDERVALUED).
    """
    from tools.analysis import calculate_fair_value_range
    return calculate_fair_value_range.invoke({
        "pe_ratio": pe_ratio,
        "price": price,
        "sector": sector,
    })


@mcp.tool()
async def get_position_sizing(
    portfolio_value: float,
    risk_score: float,
    conviction: str = "medium",
) -> dict:
    """
    Recommend position sizing (allocation %) for a stock given portfolio size,
    risk score, and investment conviction level (low/medium/high).
    """
    from tools.analysis import generate_position_sizing
    return generate_position_sizing.invoke({
        "portfolio_value": portfolio_value,
        "risk_score": risk_score,
        "conviction": conviction,
    })


# ── Tool manifest endpoint ─────────────────────────────────────────────────
@mcp.resource("tools://manifest")
def tool_manifest() -> dict:
    """Lists all available tools with their descriptions."""
    return {
        "server": settings.mcp_server_name,
        "total_tools": 10,
        "categories": {
            "market_data": ["get_stock_price", "get_historical_prices", "compare_multiple_stocks"],
            "news_research": ["get_stock_news", "get_hedging_strategies", "get_sector_outlook", "score_news_sentiment"],
            "analysis": ["get_risk_score", "get_fair_value", "get_position_sizing"],
        },
    }


if __name__ == "__main__":
    print(f"Starting FastMCP server '{settings.mcp_server_name}' on port {settings.mcp_port}")
    mcp.run(transport="sse", host=settings.mcp_host, port=settings.mcp_port)