import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.state import AgentState
from core.config import settings
from agents.chat_node            import chat_node
from agents.curent_market_data_node     import market_data_node
from agents.search_node          import search_node
from agents.analysis_node         import analyst_node
from agents.risk_mitigation_node import risk_mitigation_node
from agents.repoter_node        import reporter_node

logger = logging.getLogger(__name__)


# ── Routing function ──────────────────────────────────────────────────────────

def route_after_analyst(state: AgentState) -> str:
    """
    Conditional edge: decides next node after analyst assessment.
    risk_flag True  → risk_mitigation (hedging research)
    risk_flag False → reporter (straight to output)
    """
    if state.get("risk_flag"):
        logger.info("[router] risk_flag=True → risk_mitigation")
        return "risk_mitigation"
    logger.info("[router] risk_flag=False → reporter")
    return "reporter"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(checkpointer=None):
    """
    Build and compile the StateGraph.

    Parameters
    ----------
    checkpointer : LangGraph checkpointer (AsyncSqliteSaver recommended)

    Returns
    -------
    Compiled LangGraph app ready for async invocation.
    """
    g = StateGraph(AgentState)

    # ── Register all nodes ────────────────────────────────────────────────
    g.add_node("chat_node",        chat_node)           # Node 0 – NEW
    g.add_node("market_data",      market_data_node)    # Node 1
    g.add_node("search",           search_node)         # Node 2
    g.add_node("analyst",          analyst_node)        # Node 3
    g.add_node("risk_mitigation",  risk_mitigation_node)# Node 4 (conditional)
    g.add_node("reporter",         reporter_node)       # Node 5 (terminal)

    # ── Deterministic edges ───────────────────────────────────────────────
    g.add_edge(START,          "chat_node")
    g.add_edge("chat_node",    "market_data")
    g.add_edge("market_data",  "search")
    g.add_edge("search",       "analyst")

    # ── Conditional edge after analyst ────────────────────────────────────
    g.add_conditional_edges(
        "analyst",
        route_after_analyst,
        {
            "risk_mitigation": "risk_mitigation",
            "reporter":        "reporter",
        },
    )

    g.add_edge("risk_mitigation", "reporter")
    g.add_edge("reporter",        END)

    return g.compile(checkpointer=checkpointer)


async def get_compiled_graph():
    global _compiled_graph

    if _compiled_graph is None:
        checkpointer = AsyncSqliteSaver.from_conn_string(settings.sqlite_db_path)
        _compiled_graph = build_graph(checkpointer=checkpointer)

    return _compiled_graph