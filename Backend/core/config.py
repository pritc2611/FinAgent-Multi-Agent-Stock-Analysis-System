import os
from dataclasses import dataclass, field
from dotenv import load_dotenv
from pathlib import Path

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

    # ── CORS origins ──────────────────────────────────────────────────────────
    # Covers: local dev, Docker same-host, HuggingFace Spaces, Render, Railway
    cors_origins: tuple = (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",    # frontend separate container
        "http://127.0.0.1:8080",
        "null",                     # file:// origin
    )

    # Regex covers HuggingFace Spaces (*.hf.space) and any reverse proxy
    cors_origin_regex: str = r"https?://.*\.(hf\.space|huggingface\.co|vercel\.app|railway\.app|onrender\.com)(:\d+)?"

    # ── SQLite checkpoint DB ──────────────────────────────────────────────────
    sqlite_db_path: str = field(
        default_factory=lambda: str(Path(__file__).resolve().parents[1] / "DB" / "finagent_checkpoints.db")
    )

    max_concurrent_runs: int = field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_RUNS", "3")))

    # ── FastMCP server ────────────────────────────────────────────────────────
    mcp_server_name: str = "finagent-tools"
    mcp_host:        str = "0.0.0.0"
    mcp_port:        int = 8001


settings = Settings()