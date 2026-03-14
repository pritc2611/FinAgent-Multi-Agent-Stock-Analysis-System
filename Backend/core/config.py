import os
from dataclasses import dataclass, field
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # ── LLM ──────────────────────────────────────────────────────────────────
    api_key:         str   = field(default_factory=lambda: os.environ.get("API_KEY", ""))
    llm_model:       str   = "openai/gpt-oss-20b"
    llm_temperature: float = 0.2
    llm_max_tokens:  int   = 2048

    # ── Server ───────────────────────────────────────────────────────────────
    api_host:  str = "0.0.0.0"
    # HuggingFace Spaces exposes port 7860; override with PORT env var locally
    api_port:  int = field(default_factory=lambda: int(os.environ.get("PORT", 7860)))
    api_title: str = "FinAgent – Multi-Agent Financial Analysis"

    # ── SQLite checkpoint DB ─────────────────────────────────────────────────
    sqlite_db_path: str = field(
        default_factory=lambda: str(
            Path(__file__).resolve().parents[1] / "DB" / "finagent_checkpoints.db"
        )
    )

    max_concurrent_runs: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_RUNS", "3"))
    )

    # ── FastMCP (internal only — not exposed publicly on HF Spaces) ──────────
    mcp_server_name: str = "finagent-tools"
    mcp_host:        str = "0.0.0.0"
    mcp_port:        int = 8001


settings = Settings()