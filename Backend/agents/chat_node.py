import json
import re
import logging
from datetime import datetime

from core.state import AgentState
from core.LLMS import get_llm
from langchain_core.messages import HumanMessage , ToolMessage , AIMessage

logger = logging.getLogger(__name__)

def llm_with_tools(tools):
    async def chat_node(state: AgentState) -> AgentState:
        """
        Node 0 – Chat Node (Tool-aware)

        Responsibilities:
        - Initialize conversation
        - Let LLM decide whether to call tools
        - Append AI response to messages
        - DO NOT parse output here
        """

        logger.info("[chat_node] running")

        errors = list(state.get("errors", []))
        messages = state.get("messages", [])

        try:
        # ── First run: inject system + user message ───────────────────────
            if not messages:
                query = (state.get("user_query") or "").strip()
                
                logger.info(f"[chat_node] New query: {query!r}")

                system_prompt = (
                "You are a financial assistant.\n\n"
                "Your job:\n"
                "- Identify the company and ticker from user input\n"
                "- If ticker is NOT clearly known → MUST call tool `get_ticker_from_company_name`\n"
                "- DO NOT guess ticker\n\n"
                "After tool result:\n"
                "- Respond with company name, ticker, and a short acknowledgement\n"
                "- Keep response simple and user-friendly"
                )

                messages = [
                {"role": "system", "content": system_prompt},
                HumanMessage(content=query)
                ]

        # ── Bind ACTUAL tools (not ToolNode) ──────────────────────────────
                llm = get_llm(bind_tools=tools)

        # ── Call LLM ──────────────────────────────────────────────────────
                response = await llm.ainvoke(messages)

                logger.info("[chat_node] LLM response received")

        # ── Append response to message history ────────────────────────────
            return {
            **state,
            "messages": messages + [response],
            "errors": errors,
            "started_at": state.get("started_at") or datetime.utcnow().isoformat(),
        }

        except Exception as exc:
            logger.error(f"[chat_node] Failed: {exc}")
            errors.append(f"chat_node: {exc}")
            
            return {
                **state,
                "errors": errors,
                }
    return chat_node

# ── Helpers ───────────────────────────────────────────────────────────────

async def extract_node(state: AgentState) -> AgentState:
    """
    Extract ticker, company, and response AFTER tool execution loop
    """

    messages = state.get("messages", [])

    ticker = None
    company_name = None
    chat_response = ""

    # ── 1. Get ticker from tool result ───────────────────────────────────
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "get_ticker_from_name":
            ticker = msg.content.strip().upper()
            break

    # ── 2. Get final AI response ─────────────────────────────────────────
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            chat_response = msg.content
            break

    # ── 3. Fallback handling ─────────────────────────────────────────────
    if not ticker:
        ticker = "UNKNOWN"

    if not company_name:
        company_name = ticker

    return {
        **state,
        "ticker": ticker,
        "company_name": company_name,
        "chat_response": chat_response,
    }