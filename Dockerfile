# ── FinAgent — Single-container HuggingFace Space ─────────────────────────────
# Everything runs on port 7860 (HF's exposed port).
# FastAPI serves both the REST/SSE API and the frontend static files.
# No separate frontend server needed.

FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY Backend/requirements.txt .
RUN pip install --prefix=/deps -r requirements.txt


# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.10-slim

WORKDIR /app

COPY --from=builder /deps /usr/local
ENV PATH=/usr/local/bin:$PATH

# Copy backend source
COPY Backend/ .

# Copy frontend INTO the backend directory so FastAPI can find and serve it
COPY frontend/ ./frontend/

# HuggingFace Spaces requires a non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 7860
ENV PORT=7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]