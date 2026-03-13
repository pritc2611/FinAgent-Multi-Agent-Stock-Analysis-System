"""
main.py
───────
FastAPI application entry point.
Mounts: REST API routes + static HTML frontend + MCP tool server (on separate port).

Start with:
    uvicorn main:app --reload --port 8000

Then open the frontend:
    Option A (simplest): open frontend/index.html directly in your browser
    Option B: visit http://localhost:8000/app  (served by FastAPI StaticFiles)
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.config import settings
from api.routes import router
from agents.Build_graph import build_graph
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("="*60)
    # conn = await aiosqlite.connect(
    #     "Multi-Agent-Financial-Analysis-System\Backend\DB\finagent_checkpoints.db"
    # )

    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        app.state.graph = build_graph(checkpointer=checkpointer)
        logger.info(f"  FinAgent API starting on port {settings.api_port}")
        logger.info(f"  MCP Tool Server on port {settings.mcp_port}")
        logger.info("="*60)
        yield
    logger.info("FinAgent API shutting down.")


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.api_title,
    description=(
        "Multi-Agent Financial Analysis System.\n\n"
        "Architecture: LangGraph async pipeline → FastMCP tool binding → "
        "SSE streaming to vanilla HTML/CSS/JS frontend."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=r"null",   # allow file:// origin (index.html opened from disk)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Mount routes ───────────────────────────────────────────────────────────────
app.include_router(router)

# ── Serve the vanilla HTML frontend at /app ────────────────────────────────────
# This lets users visit http://localhost:8000/app as an alternative to
# opening index.html directly from disk.
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/app", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


@app.get("/", tags=["Health"])
async def root():
    return {
        "service":    "FinAgent API",
        "status":     "ok",
        "docs":       "/docs",
        "frontend":   "/app  (or open frontend/index.html directly)",
        "mcp_server": f"http://localhost:{settings.mcp_port}",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


# ── Dev runner ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info",
    )