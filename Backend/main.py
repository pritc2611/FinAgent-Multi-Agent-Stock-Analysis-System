"""
main.py  –  FinAgent FastAPI entry point
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from api.routes import router
from agents.Build_graph import build_graph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        app.state.graph = build_graph(checkpointer=checkpointer)
        logger.info("=" * 60)
        logger.info(f"  FinAgent API starting on port {settings.api_port}")
        logger.info(f"  MCP Tool Server on port {settings.mcp_port}")
        logger.info("=" * 60)
        yield
    logger.info("FinAgent API shutting down.")


app = FastAPI(
    title=settings.api_title,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# allow_origins=["*"] is safe here because this is a read-only analysis API
# with no authentication/cookies. Tighten in production if needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],                        # covers HF Spaces, Docker, etc.
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,                    # must be False when origins="*"
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(router)

# Serve frontend at /app  (fallback when not using separate frontend container)
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/app", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


@app.get("/", tags=["Health"])
async def root():
    return {
        "service":    "FinAgent API",
        "status":     "ok",
        "docs":       "/docs",
        "frontend":   "/app",
        "mcp_server": f"http://localhost:{settings.mcp_port}",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info",
    )