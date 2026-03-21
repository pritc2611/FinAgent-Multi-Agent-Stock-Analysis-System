import asyncio
from typing import Optional
import yfinance as yf
from langchain_core.tools import tool
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

import re

def get_ticker_from_name(company_name):
    query = f"SYMBOL OF {company_name} STOCK - FROM YAHOO FINANCE".upper()
    
    with DDGS() as ddgs:
        # Search for the top 5 results
        results = ddgs.text(query, max_results=5)
        
        for result in results:
            text_to_check = result['body'] + " " + result['title']
            
            # Pattern to find potential tickers (2-5 uppercase letters) 
            # often found in parentheses or after "ticker:" or "NASDAQ:"
            match = re.search(r'\(([A-Z]{1,5})\)', text_to_check)
            
            if match:
                # Return the first group that matched
                ticker = next(group for group in match.groups() if group is not None)
                return ticker
                
    return "Ticker not found"

@tool
async def fetch_market_data(ticker: str) -> dict:
    """
    Fetch live market data for a stock ticker using yfinance.

    Returns current price, 52-week high/low, P/E ratio, market cap,
    volume, and company name. Use this whenever the user asks about
    Fetch live market data for an exact stock ticker using yfinance.
    
    Args:
        ticker: Exchange-specific stock symbol (e.g. AAPL, RELIANCE.NS, 7203.T)
    """
    def _blocking_fetch():
        symbol = (ticker or "").upper().strip()
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        
        return {
            "ticker": symbol,
            "company_name": info.get("longName", symbol),
            "price": _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
            "week52_high": _safe_float(info.get("fiftyTwoWeekHigh")),
            "week52_low": _safe_float(info.get("fiftyTwoWeekLow")),
            "pe_ratio": _safe_float(info.get("trailingPE")),
            "market_cap": info.get("marketCap"),
            "volume": info.get("volume"),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
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
        hist = stock.history(period=period)
        if hist.empty:
            return {"error": f"No historical data for {ticker}"}
        return {
            "ticker": ticker.upper(),
            "period": period,
            "dates": hist.index.strftime("%Y-%m-%d").tolist(),
            "open": hist["Open"].round(2).tolist(),
            "high": hist["High"].round(2).tolist(),
            "low": hist["Low"].round(2).tolist(),
            "close": hist["Close"].round(2).tolist(),
            "volume": hist["Volume"].tolist(),        }

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