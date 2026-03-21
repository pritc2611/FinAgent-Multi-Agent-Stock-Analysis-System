from tools.curent_market_data import fetch_market_data, fetch_historical_prices, compare_stocks
from tools.search_news import search_stock_news, search_hedging_strategies, search_sector_analysis, analyze_sentiment
from tools.analysis    import calculate_risk_score, calculate_fair_value_range, generate_position_sizing
from tools.ticker_resolver import resolve_ticker_symbol

# ── Master registry ────────────────────────────────────────────────────────
ALL_TOOLS: list = [
    # Market data tools
    fetch_market_data,
    fetch_historical_prices,
    compare_stocks,

    # ticker resolver
    resolve_ticker_symbol,

    # News & search tools
    search_stock_news,
    search_hedging_strategies,
    search_sector_analysis,
    analyze_sentiment,

    # Analysis & calculation tools
    calculate_risk_score,
    calculate_fair_value_range,
    generate_position_sizing,
]

TOOL_NAMES = [t.name for t in ALL_TOOLS]

__all__ = ["ALL_TOOLS", "TOOL_NAMES"]