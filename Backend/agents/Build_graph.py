import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.state import AgentState
from core.config import settings
from agents.current_market_data_node     import market_data_node
from agents.search_node          import search_node
from agents.analysis_node         import analyst_node
from agents.risk_mitigation_node import risk_mitigation_node
from agents.reporter_node        import reporter_node
from langgraph.prebuilt import tools_condition , ToolNode 
from langchain_mcp_adapters.client import MultiServerMCPClient
from agents.chat_node import extract_node , llm_with_tools
import asyncio

logger = logging.getLogger(__name__)

# _ASYNC_LOOP = asyncio.new_event_loop()


# def _submit_async(coro):
#     return asyncio.run_coroutine_threadsafe(coro, _ASYNC_LOOP)


# def run_async(coro):
#     return _submit_async(coro).result()


clients = MultiServerMCPClient(
    {
        "my_custom_tools": {
            "command": "python",
            "args": ["MCP-servers/servers.py"], # Path to your FastMCP file
            "transport": "stdio",
        },
        
    }

)


_tools_cache = None
_lock = asyncio.Lock()

async def get_mcp_tools():
    global _tools_cache

    if _tools_cache is not None:
        return _tools_cache

    async with _lock:
        if _tools_cache is None:
            _tools_cache = await clients.get_tools()

    return _tools_cache

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

def build_graph(checkpointer,mcp_tools):
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

    # ✅ Create ToolNode with REAL tools
    tools = ToolNode(tools=mcp_tools)

    # ✅ Inject tools into chat node via closure
    chat_node = llm_with_tools(mcp_tools)


    # ── Register all nodes ────────────────────────────────────────────────
    g.add_node("chat_node",        chat_node)           # Node 0 – NEW
    g.add_node("market_data",      market_data_node)    # Node 1
    g.add_node("search",           search_node)         # Node 2
    g.add_node("analyst",          analyst_node)        # Node 3
    g.add_node("risk_mitigation",  risk_mitigation_node)# Node 4 (conditional)
    g.add_node("reporter",         reporter_node)       # Node 5 (terminal)
    g.add_node("tools",                tools)       # Node 6 (tools container)
    g.add_node("extractore",      extract_node)         # Node 7 (extract of ticker)

    # ── Deterministic edges ───────────────────────────────────────────────
    g.add_edge(START,          "chat_node")
    g.add_conditional_edges("chat_node",tools_condition)
    g.add_edge("tools","chat_node")
    g.add_edge("chat_node", "extractore")
    g.add_edge("extractore",    "market_data")
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

