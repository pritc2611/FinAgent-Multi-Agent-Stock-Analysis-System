from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════
# LangGraph State
# ═══════════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    """
    Canonical state object that flows through all graph nodes.
    Every node receives a copy and returns an updated copy.
    """
    # ── Input (set by API before graph starts) ────────────────────────────
    user_query:          str               # raw text from user chat input

    # ── Populated by Chat_Node (Node 0) ──────────────────────────────────
    ticker:              Optional[str]     # extracted ticker symbol e.g. "AAPL"
    company_name:        Optional[str]     # full company name e.g. "Apple Inc."
    chat_response:       Optional[str]     # friendly acknowledgement for the UI

    # ── Populated by Market_Data_Node (Node 1) ────────────────────────────
    financial_data:      Optional[dict]    # price, 52W hi/lo, P/E …

    # ── Populated by Search_Node (Node 2) ────────────────────────────────
    news_headlines:      Optional[list[str]]
    sentiment_score:     Optional[float]   # –1.0 (bearish) … +1.0 (bullish)

    # ── Populated by Analyst_Node (Node 3) ───────────────────────────────
    risk_flag:           Optional[bool]    # True → route via risk_mitigation
    analyst_rationale:   Optional[str]

    # ── Populated by Risk_Mitigation_Node (Node 4, conditional) ──────────
    hedging_strategies:  Optional[str]

    # ── Populated by Reporter_Node (Node 5, terminal) ─────────────────────
    investment_memo:     Optional[str]

    # ── Accumulated non-fatal errors ──────────────────────────────────────
    errors:              list[str]

    # ── Run metadata ──────────────────────────────────────────────────────
    run_id:              Optional[str]
    started_at:          Optional[str]
    completed_at:        Optional[str]


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic – API request / response models
# ═══════════════════════════════════════════════════════════════════════════

class AnalysisRequest(BaseModel):
    """
    Accepts a free-text natural language query from the chat UI.
    The chat_node extracts the ticker symbol from this query.
    """
    query: str = Field(
        ...,
        example="What do you think about Apple stock right now?",
        description="Natural language query — company name or question about a stock",
    )


class FinancialDataModel(BaseModel):
    price:        Optional[float] = None
    week52_high:  Optional[float] = None
    week52_low:   Optional[float] = None
    pe_ratio:     Optional[float] = None
    company_name: Optional[str]   = None
    sector:       Optional[str]   = None
    market_cap:   Optional[float] = None


class AnalysisResponse(BaseModel):
    run_id:              str
    ticker:              Optional[str]    = None
    company_name:        Optional[str]    = None
    user_query:          Optional[str]    = None
    chat_response:       Optional[str]    = None
    status:              str                      # "completed" | "error"
    financial_data:      Optional[FinancialDataModel] = None
    news_headlines:      Optional[list[str]] = None
    sentiment_score:     Optional[float]     = None
    risk_flag:           Optional[bool]      = None
    analyst_rationale:   Optional[str]       = None
    hedging_strategies:  Optional[str]       = None
    investment_memo:     Optional[str]       = None
    errors:              list[str]           = []
    started_at:          Optional[str]       = None
    completed_at:        Optional[str]       = None


class AnalysisStatusResponse(BaseModel):
    run_id:        str
    ticker:        Optional[str] = None
    status:        str                    # "pending" | "running" | "completed" | "error"
    progress_step: Optional[str] = None  # current node name


class ErrorResponse(BaseModel):
    detail: str
