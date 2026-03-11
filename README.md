# FinAgent — Multi-Agent Stock Analysis System

FinAgent is a production-oriented multi-agent financial analysis platform that combines a LangGraph workflow backend, MCP-exposed tool integrations, and a premium web console frontend with live SSE progress streaming.

It is designed to run in:
- **Single-container mode** (backend serves frontend at `/app`) for simple deployment.
- **Split-container mode** (frontend + backend independently scalable) using configurable API base URL.

---

## ✨ Highlights

- **Multi-agent analysis pipeline** powered by LangGraph.
- **Live run streaming** to the UI using Server-Sent Events (SSE).
- **Financial + news + risk workflow** with conditional routing for hedging recommendations.
- **MCP tool server** exposing market/news/analysis tools for agent tool calling.
- **Premium frontend console** with run telemetry, timeline progress, and result panels.
- **Container-ready communication model** with same-origin and cross-origin deployment support.
- SQLite-backed LangGraph checkpoints are persisted on disk and survive service restarts until the checkpoint DB file is manually deleted.

---

## 🧠 System Architecture

### Agent Workflow (LangGraph)

```text
START
  -> chat_node
  -> market_data
  -> search
  -> analyst
      ├─ if risk_flag=True  -> risk_mitigation
      └─ if risk_flag=False -> reporter
  -> END
```

### Runtime Components

- **FastAPI app (`Backend/main.py`)**
  - REST API endpoints
  - SSE stream endpoint
  - Optional static frontend hosting at `/app`
- **Analysis routes (`Backend/api/routes.py`)**
  - Job lifecycle, progress, results, in-memory history
- **MCP Server (`Backend/MCP-servers/servers.py`)**
  - Exposes callable tool endpoints for data/research/analysis
- **Frontend (`frontend/`)**
  - Production-grade console in HTML/CSS/JS

---

## 📁 Project Structure

```text
Backend/
  agents/            # graph nodes + graph construction
  api/               # REST/SSE endpoints
  core/              # config + state models + LLM setup
  tools/             # market/news/analysis tool implementations
  MCP-servers/       # FastMCP server
  main.py            # FastAPI entrypoint
frontend/
  index.html         # app shell
  main.js            # API + SSE integration
  styles.css         # premium responsive UI
README.md
```

---

## 🔌 API Overview

Base path: `/api/v1`

- `POST /analyse` — start async analysis run (`query`, optional `thread_id` for persistent memory scope)
- `GET /stream/{run_id}` — SSE events (`progress`, `ticker`, `complete`, `error`)
- `GET /status/{run_id}` — poll run status
- `GET /result/{run_id}` — fetch final result
- `GET /jobs` — recent jobs summary
- `GET /history` — in-memory history
- `DELETE /history` — clear history
- `GET /tools` — list registered tools

Health endpoints:
- `GET /`
- `GET /health`

Interactive docs:
- `/docs` (Swagger)
- `/redoc`

---

## ⚙️ Configuration

Environment variables are loaded from `.env` (via `python-dotenv`).

| Variable | Description | Default |
|---|---|---|
| `API_KEY` | LLM provider API key | `""` |
| `MAX_CONCURRENT_RUNS` | Max concurrent background analysis runs | `3` |

Built-in defaults in config:
- API host/port: `0.0.0.0:8000`
- MCP host/port: `0.0.0.0:8001`
- SQLite checkpointer path: `DB/finagent_checkpoints.db`

> Note: checkpoints persist in the SQLite file, while `_jobs` and `_history` endpoint stores are still in-memory and reset on server restart.

---

## 🚀 Local Development

## 1) Install dependencies

If you already manage dependencies with your own lockfile/tooling, keep using that. Otherwise, install the primary runtime packages:

```bash
pip install fastapi uvicorn sse-starlette python-dotenv langgraph langchain-core fastmcp yfinance ddgs duckduckgo-search
```

## 2) Configure environment

Create `.env` in the project root:

```bash
API_KEY=your_api_key_here
MAX_CONCURRENT_RUNS=3
```

## 3) Start backend

```bash
cd Backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 4) Open frontend

Choose one:
- **Recommended:** `http://localhost:8000/app`
- Or open `frontend/index.html` directly

---

## 🐳 Deployment Patterns

### A) Single Image / Same-Origin (simplest)

- Serve frontend from backend (`/app`)
- Browser calls relative API paths (no CORS complexity)
- Best for straightforward packaging and operations

### B) Split Frontend + Backend Containers (scalable)

- Deploy frontend and backend independently
- Set **API Base URL** in frontend connection settings (e.g. `https://api.yourdomain.com`)
- Configure backend `allow_origins` appropriately for your frontend domain
- Put both behind a reverse proxy / ingress if needed

---

## 📡 SSE Event Contract (Frontend Integration)

From `GET /api/v1/stream/{run_id}`:

- `progress`:
  ```json
  { "node": "search", "status": "running" }
  ```
- `ticker`:
  ```json
  { "ticker": "AAPL", "company_name": "Apple Inc.", "chat_response": "..." }
  ```
- `complete`:
  ```json
  { "run_id": "...", "status": "completed", "financial_data": { ... }, "investment_memo": "..." }
  ```
- `error`:
  ```json
  { "detail": "..." }
  ```

---

## 🔒 Production Notes

- Restrict CORS allowlist before production internet exposure.
- Add authentication/authorization for API access.
- Use durable persistence for jobs/history/checkpoints (not only in-memory).
- Add centralized logging + monitoring + alerts.
- Add request/rate limits and input validation hardening.

---

## 🧪 Quick Sanity Checks

```bash
# Backend health
curl http://localhost:8000/health

# Start run (use stable thread_id for persistent memory across runs)
curl -X POST http://localhost:8000/api/v1/analyse \
  -H 'Content-Type: application/json' \
  -d '{"query":"Analyze Apple stock for this month","thread_id":"demo-user-1"}'

# List jobs
curl http://localhost:8000/api/v1/jobs
```
