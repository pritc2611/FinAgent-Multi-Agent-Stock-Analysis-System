import asyncio
import json
import uuid
import logging
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from core.state import (
    AgentState, AnalysisRequest, AnalysisResponse,
    FinancialDataModel, AnalysisStatusResponse
)
from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Analysis"])

# ── In-memory stores ──────────────────────────────────────────────────────────
_jobs:    dict[str, dict] = {}   # run_id → job metadata + result
_history: list[dict]      = []   # ordered chat session history (latest last)

# ── Concurrency guard ─────────────────────────────────────────────────────────
_semaphore = asyncio.Semaphore(3)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/analyse", response_model=dict, summary="Start async analysis from natural-language query")
async def start_analysis(request: Request, payload: AnalysisRequest):
    """
    Kick off a full multi-agent analysis run asynchronously.
    Accepts a free-text query like "What do you think about Apple stock?"
    The chat_node will extract the ticker symbol.
    Returns run_id immediately; stream progress via /stream/{run_id}.
    """
    run_id = str(uuid.uuid4())
    query = payload.query.strip()
    thread_id = (payload.thread_id or "").strip() or run_id
    graph = request.app.state.graph
    _jobs[run_id] = {
        "run_id":        run_id,
        "user_query":    query,
        "ticker":        None,  
        "status":        "pending",
        "thread_id":     thread_id,
        "progress_step": None,
        "result":        None,
        "error":         None,
        "created_at":    datetime.utcnow().isoformat(),
    }

    # Record in session history immediately (will be updated on completion)
    _history.append({
        "run_id":     run_id,
        "user_query": query,
        "ticker":     None,
        "status":     "pending",
        "created_at": datetime.utcnow().isoformat(),
        "result":     None,
    })

    # Fire-and-forget async task
    asyncio.create_task(_run_analysis(run_id, query, thread_id,graph))

    return {"run_id": run_id, "user_query": query, "status": "pending"}


@router.get("/status/{run_id}", response_model=AnalysisStatusResponse)
async def get_status(run_id: str):
    """Poll the status of a running or completed analysis."""
    job = _get_job_or_404(run_id)
    return AnalysisStatusResponse(
        run_id=run_id,
        ticker=job.get("ticker"),
        status=job["status"],
        progress_step=job.get("progress_step"),
    )


@router.get("/result/{run_id}", response_model=AnalysisResponse)
async def get_result(run_id: str):
    """Retrieve the full result of a completed analysis."""
    job = _get_job_or_404(run_id)
    if job["status"] not in ("completed", "error"):
        raise HTTPException(status_code=202, detail="Analysis still running")
    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=job.get("error", "Unknown error"))
    return _state_to_response(job["result"])


@router.get("/stream/{run_id}", summary="SSE stream of analysis progress + completion")
async def stream_analysis(run_id: str, request: Request):
    """
    Server-Sent Events stream.

    Events emitted:
      progress  → { node, status }          (one per agent node)
      ticker    → { ticker, company_name, chat_response }   (after chat_node)
      complete  → full AnalysisResponse JSON
      error     → { detail }
    """
    _get_job_or_404(run_id)

    async def event_generator() -> AsyncGenerator[dict, None]:
        prev_step       = None
        ticker_sent     = False

        while True:
            if await request.is_disconnected():
                break

            job       = _jobs.get(run_id, {})
            status    = job.get("status")
            curr_step = job.get("progress_step")

            # Emit ticker event as soon as chat_node sets it
            if not ticker_sent and job.get("ticker"):
                result = job.get("result") or {}
                yield {
                    "event": "ticker",
                    "data": json.dumps({
                        "ticker":        job["ticker"],
                        "company_name":  result.get("company_name") or job["ticker"],
                        "chat_response": result.get("chat_response", ""),
                    }),
                }
                ticker_sent = True

            # Emit progress events for each new node
            if curr_step and curr_step != prev_step:
                yield {
                    "event": "progress",
                    "data": json.dumps({"node": curr_step, "status": "running"}),
                }
                prev_step = curr_step

            if status == "completed":
                result = job.get("result", {})
                yield {
                    "event": "complete",
                    "data": json.dumps(_state_to_response(result).model_dump()),
                }
                break

            if status == "error":
                yield {
                    "event": "error",
                    "data": json.dumps({"detail": job.get("error", "Unknown error")}),
                }
                break

            await asyncio.sleep(0.4)

    return EventSourceResponse(event_generator())


@router.get("/history", summary="Session chat history (cleared on server restart)")
async def get_history():
    """
    Returns all analyses run this session, newest last.
    History is in-memory only — clears when the server restarts.
    """
    return {
        "count":   len(_history),
        "history": _history,
    }


@router.delete("/history", summary="Clear session history")
async def clear_history():
    """Clear the in-memory session history."""
    _history.clear()
    return {"cleared": True}


@router.get("/jobs", summary="List all analysis jobs (alias for history)")
async def list_jobs():
    """Return a summary of all jobs (latest 50)."""
    jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)[:50]
    return [
        {
            "run_id":        j["run_id"],
            "user_query":    j.get("user_query", ""),
            "ticker":        j.get("ticker"),
            "thread_id":     j.get("thread_id"),
            "status":        j["status"],
            "created_at":    j["created_at"],
            "progress_step": j.get("progress_step"),
        }
        for j in jobs
    ]


@router.get("/tools", summary="List all registered MCP tools")
async def list_tools():
    """Return the full tool manifest."""
    from tools import ALL_TOOLS
    return {
        "total": len(ALL_TOOLS),
        "tools": [{"name": t.name, "description": t.description} for t in ALL_TOOLS],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _run_analysis(run_id: str, query: str , thread_id: str,graph):
    """
    Background coroutine that executes the LangGraph pipeline.
    Updates _jobs and _history dicts as nodes complete.
    """
    async with _semaphore:
        _jobs[run_id]["status"] = "running"

        try:
            app = graph

            initial_state: AgentState = {
                "user_query":        query,
                "ticker":            None,
                "company_name":      None,
                "chat_response":     None,
                "financial_data":    None,
                "news_headlines":    None,
                "sentiment_score":   None,
                "risk_flag":         None,
                "analyst_rationale": None,
                "hedging_strategies":None,
                "investment_memo":   None,
                "errors":            [],
                "run_id":            run_id,
                "started_at":        datetime.utcnow().isoformat(),
                "completed_at":      None,
            }

            config      = {"configurable": {"thread_id": thread_id}}
            final_state = dict(initial_state)

            async for event in app.astream(initial_state, config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    final_state = {**final_state, **node_output}
                    _jobs[run_id]["progress_step"] = node_name
                    _jobs[run_id]["result"]        = final_state

                    # Expose ticker as soon as chat_node sets it
                    if node_name == "chat_node" and final_state.get("ticker"):
                        _jobs[run_id]["ticker"] = final_state["ticker"]

                    logger.info(f"[run {run_id}] Node completed: {node_name}")

            _jobs[run_id]["status"]        = "completed"
            _jobs[run_id]["result"]        = final_state
            _jobs[run_id]["progress_step"] = "reported"

            # Update history entry
            _update_history(run_id, final_state)

        except Exception as exc:
            logger.error(f"[run {run_id}] Failed: {exc}")
            _jobs[run_id]["status"] = "error"
            _jobs[run_id]["error"]  = str(exc)
            _update_history(run_id, None, error=str(exc))


def _update_history(run_id: str, state: dict | None, error: str = ""):
    """Update the history entry for a run."""
    for entry in _history:
        if entry["run_id"] == run_id:
            if state:
                entry["ticker"]  = state.get("ticker")
                entry["status"]  = "completed"
                entry["result"]  = _state_to_response(state).model_dump()
            else:
                entry["status"]  = "error"
                entry["error"]   = error
            break


def _get_job_or_404(run_id: str) -> dict:
    job = _jobs.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Run ID '{run_id}' not found")
    return job


def _state_to_response(state: dict) -> AnalysisResponse:
    fd = state.get("financial_data") or {}
    return AnalysisResponse(
        run_id=state.get("run_id", ""),
        ticker=state.get("ticker"),
        company_name=state.get("company_name") or fd.get("company_name"),
        user_query=state.get("user_query"),
        chat_response=state.get("chat_response"),
        status="completed",
        financial_data=FinancialDataModel(
            price=fd.get("price"),
            week52_high=fd.get("week52_high"),
            week52_low=fd.get("week52_low"),
            pe_ratio=fd.get("pe_ratio"),
            company_name=fd.get("company_name"),
            sector=fd.get("sector"),
            market_cap=fd.get("market_cap"),
            currency=fd.get("currency"),
        ) if fd else None,
        news_headlines=state.get("news_headlines"),
        sentiment_score=state.get("sentiment_score"),
        risk_flag=state.get("risk_flag"),
        analyst_rationale=state.get("analyst_rationale"),
        hedging_strategies=state.get("hedging_strategies"),
        investment_memo=state.get("investment_memo"),
        errors=state.get("errors", []),
        started_at=state.get("started_at"),
        completed_at=state.get("completed_at"),
    )