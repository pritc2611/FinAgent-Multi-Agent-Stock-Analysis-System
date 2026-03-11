import logging
from datetime import datetime
from core.state import AgentState
from tools.curent_market_data import fetch_market_data

logger = logging.getLogger(__name__)


async def market_data_node(state: AgentState) -> AgentState:
    """
    Node 1 – Market Data
    Fetches price, 52W hi/lo, P/E, sector from yfinance.
    Populates: state["financial_data"]
    """
    ticker = state["ticker"].upper()
    logger.info(f"[market_data_node] Fetching data for {ticker}")

    try:
        data = await fetch_market_data.ainvoke({"ticker": ticker})
        logger.info(f"[market_data_node] ✓ {data}")
        return {
            **state,
            "financial_data": data,
            "started_at": state.get("started_at") or datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error(f"[market_data_node] ✗ {exc}")
        return {
            **state,
            "financial_data": {},
            "errors": state.get("errors", []) + [f"market_data_node: {exc}"],
        }