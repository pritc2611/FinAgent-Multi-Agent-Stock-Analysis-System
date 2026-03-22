"""
main.py  ─  FinAgent FastAPI entry point
─────────────────────────────────────────────────────────────────────────────
HuggingFace Spaces exposes ONE port (7860).
This file runs EVERYTHING on that single port:
  • /health     → health check
  • /api/v1/*   → LangGraph agent pipeline (REST + SSE)
  • /docs       → Swagger UI
  • /*          → frontend static files (index.html, style.css, script.js)
"""

import logging
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from core.config import settings
from api.routes import router
from agents.Build_graph import build_graph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# HuggingFace Spaces exposes port 7860; local dev can use 8000
PORT = int(os.environ.get("PORT", 7860))


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.path.dirname(settings.sqlite_db_path), exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(settings.sqlite_db_path) as checkpointer:
        app.state.graph = build_graph(checkpointer=checkpointer)
        logger.info("=" * 60)
        logger.info(f"  FinAgent running on port {PORT}")
        logger.info(f"  API docs at /docs")
        logger.info("=" * 60)
        yield
    logger.info("FinAgent shutting down.")



app = FastAPI(
    title=settings.api_title,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS: wildcard is safe — no auth cookies used
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# API routes registered BEFORE static mount so they take priority
app.include_router(router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


# Find the frontend directory — works for local dev, Docker, and HF Spaces
_candidates = [
    Path(__file__).parent / "frontend",           # HF Space: frontend/ next to main.py
    Path(__file__).parent.parent / "frontend",    # local dev: sibling directory
    Path("/app/frontend"),                         # Docker absolute path
]
_frontend_dir = next((p for p in _candidates if p.exists()), None)

if _frontend_dir:
    logger.info(f"Serving frontend from: {_frontend_dir}")
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
else:
    logger.warning("Frontend directory not found — API only mode.")

    @app.get("/")
    async def root():
        return {"service": "FinAgent API", "status": "ok", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False, log_level="info")