import asyncio
from typing import Optional
import yfinance as yf
from langchain_core.tools import tool
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

import re

@tool
def get_ticker_from_name(company_name):
    """
    if user give any company name which you dosen't know the ticker of that company
    so use this tool to find the company ticker symbole

    this tool return the title and body where the company ticker symbole container in capital words
    
    and use the output and find the COMPANY TICKER SYMBOL
    Args:
        company_name : company name without spelling misteks 
    """
    query = f"SYMBOL OF {company_name} STOCK - FROM YAHOO FINANCE".upper()
    title = []
    body = []
    with DDGS() as ddgs:
        # Search for the top 5 results
        results = ddgs.text(query, max_results=3)
        
        for i, r in enumerate(results, 3):
            title.append(f"{i}. {r['title']}")
            body.append(f"   Snippet: {r['body']}\n")
    return {"title":title,"body":body} 

@tool
async def fetch_market_data(ticker: str) -> dict:
    """
    Fetch live market data for a stock ticker using yfinance.

    Returns current price, 52-week high/low, P/E ratio, market cap,
    volume, and company name. Use this whenever the user asks about
    stock price, valuation metrics, or market performance.

    Args:
        ticker: Stock symbol (e.g. AAPL, NVDA, TSLA)
    """
    def _blocking_fetch():
        stock = yf.Ticker(ticker.upper())
        info  = stock.info
        return {
            "ticker":       ticker.upper(),
            "company_name": info.get("longName", ticker),
            "price":        _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
            "week52_high":  _safe_float(info.get("fiftyTwoWeekHigh")),
            "week52_low":   _safe_float(info.get("fiftyTwoWeekLow")),
            "pe_ratio":     _safe_float(info.get("trailingPE")),
            "market_cap":   info.get("marketCap"),
            "volume":       info.get("volume"),
            "sector":       info.get("sector", "Unknown"),
            "industry":     info.get("industry", "Unknown"),
            "currency":     info.get("currency")
        }

    # Run blocking yfinance I/O in a thread pool to keep the event loop free
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _blocking_fetch)


@tool
async def fetch_historical_prices(ticker: str, period: str = "3mo") -> dict:
    """
    Fetch historical OHLCV price data for charting or trend analysis.

    Args:
        ticker: Stock symbol (e.g. AAPL)
        period: Time period - valid values: 1mo, 3mo, 6mo, 1y, 2y, 5y
    """
    def _blocking():
        stock = yf.Ticker(ticker.upper())
        hist  = stock.history(period=period)
        if hist.empty:
            return {"error": f"No historical data for {ticker}"}
        return {
            "ticker": ticker.upper(),
            "period": period,
            "dates":  hist.index.strftime("%Y-%m-%d").tolist(),
            "open":   hist["Open"].round(2).tolist(),
            "high":   hist["High"].round(2).tolist(),
            "low":    hist["Low"].round(2).tolist(),
            "close":  hist["Close"].round(2).tolist(),
            "volume": hist["Volume"].tolist(),
            
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _blocking)


@tool
async def compare_stocks(tickers: list[str]) -> dict:
    """
    Compare key metrics across multiple stocks side-by-side.

    Args:
        tickers: List of stock symbols e.g. ["AAPL", "MSFT", "GOOGL"]
    """
    async def _fetch_one(t: str) -> dict:
        return await fetch_market_data.ainvoke({"ticker": t})

    results = await asyncio.gather(*[_fetch_one(t) for t in tickers], return_exceptions=True)
    return {
        "comparison": [
            r if not isinstance(r, Exception) else {"ticker": tickers[i], "error": str(r)}
            for i, r in enumerate(results)
        ]
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    try:
        return round(float(val), 2) if val is not None else None
    except (TypeError, ValueError):
        return None