"""
core/config.py
──────────────
Centralised application configuration loaded from environment variables.
All other modules import from here – never import os.environ directly.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # ── LLM ───────────────────────────────────────────────────────────────────
    api_key: str    = field(default_factory=lambda: os.environ.get("API_KEY", ""))
    llm_model:         str    = "openai/gpt-oss-20b"
    llm_temperature:   float  = 0.2
    llm_max_tokens:    int    = 2048

    # ── FastAPI ───────────────────────────────────────────────────────────────
    api_host:  str = "0.0.0.0"
    api_port:  int = 8000
    api_title: str = "FinAgent – Multi-Agent Financial Analysis"

    # ── CORS origins (dev; lock down in prod) ─────────────────────────────────
    cors_origins: tuple = (
        "http://localhost:8000",   # backend itself (when serving static files)
        "http://127.0.0.1:8000",
        "http://localhost:8080",   # common simple HTTP server port
        "http://127.0.0.1:8080",
        "null",                    # file:// origin (open index.html directly)
    )

    # ── SQLite checkpoint DB ──────────────────────────────────────────────────
    sqlite_db_path: str = "DB/finagent_checkpoints.db"

    max_concurrent_runs = os.getenv("MAX_CONCURRENT_RUNS", 3)

    # ── FastMCP server ────────────────────────────────────────────────────────
    mcp_server_name: str = "finagent-tools"
    mcp_host:        str = "0.0.0.0"
    mcp_port:        int = 8001


settings = Settings()
