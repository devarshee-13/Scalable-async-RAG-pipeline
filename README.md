# Scalable Async RAG Pipeline

A production-ready, async document ingestion and retrieval-augmented generation (RAG) API. Upload PDF or TXT documents, then run natural-language queries against the corpus with source citations. Ingestion runs in the background via Celery; queries use vector search (pgvector) and optional Redis caching.

## Features

- **Async document ingestion** — Upload documents and get an immediate `202 Accepted`; processing runs in Celery workers.
- **RAG over your docs** — Query in natural language; answers are grounded in uploaded content with source citations.
- **Vector search** — PostgreSQL + pgvector with HNSW index for low-latency semantic search.
- **Query caching** — Redis caches query results (1-hour TTL) for repeated questions.
- **Observability** — Prometheus metrics at `GET /metrics` (ingestion, query latency, cache hits, vector search).
- **Horizontal scaling** — Add more Celery workers to increase ingestion throughput.

## Tech Stack

| Layer        | Technology                    |
|-------------|-------------------------------|
| API         | FastAPI, Uvicorn              |
| Task queue  | Celery 5, Redis broker       |
| Database    | PostgreSQL 16, pgvector      |
| Embeddings  | sentence-transformers (e.g. all-MiniLM-L6-v2) |
| LLM         | OpenAI (e.g. gpt-4o-mini) or Ollama |
| Cache       | Redis 7                       |

## Prerequisites

- Docker and Docker Compose
- (Optional) OpenAI API key if using `LLM_BACKEND=openai`

## Quick Start

1. **Clone and enter the project**
   ```bash
   cd Scalable-async-RAG-pipeline
   ```

2. **Create a `.env` file** in the project root (see [Configuration](#configuration)).
   ```bash
   # Minimum for OpenAI LLM
   OPENAI_API_KEY=your_key_here
   LLM_BACKEND=openai
   LLM_MODEL=gpt-4o-mini
   ```

3. **Start the stack**
   ```bash
   docker compose up --build
   ```
   This runs the API, Celery worker, PostgreSQL (pgvector), and Redis.

4. **Use the API**
   - **Docs UI:** http://localhost:8000/docs
   - **Health:** http://localhost:8000/health
   - **Metrics:** http://localhost:8000/metrics

## Configuration

Settings are read from environment variables or a `.env` file. Key options:

| Variable              | Description                          | Default (example)        |
|-----------------------|--------------------------------------|--------------------------|
| `DATABASE_URL`        | PostgreSQL URL (asyncpg)             | `postgresql+asyncpg://rag:rag@postgres:5432/rag` (in Docker) |
| `REDIS_URL`           | Redis URL                            | `redis://redis:6379/0`   |
| `CELERY_BROKER_URL`   | Celery broker                        | same as `REDIS_URL`      |
| `OPENAI_API_KEY`      | Required for OpenAI LLM              | —                        |
| `LLM_BACKEND`         | `openai` or `ollama`                 | `openai`                 |
| `LLM_MODEL`           | Model name                           | `gpt-4o-mini`            |
| `OLLAMA_BASE_URL`     | Ollama API URL (if using Ollama)    | `http://ollama:11434/v1` |

When running with Docker Compose, use hostnames `postgres` and `redis` in URLs.

## API Overview

| Method | Endpoint                        | Description |
|--------|---------------------------------|-------------|
| POST   | `/documents/upload`             | Upload a PDF or TXT file (max 10 MB). Returns `doc_id` and `status: pending`. |
| GET    | `/documents/{doc_id}/status`    | Poll until `status` is `completed` or `failed` and `chunk_count` is set. |
| POST   | `/query`                        | Send `{"query": "Your question?", "doc_id": "optional-uuid", "top_k": 5}`. Returns answer, sources, `cached`, `latency_ms`. |
| GET    | `/health`                       | Liveness check. |
| GET    | `/metrics`                      | Prometheus metrics. |

### Example: Upload and query

```bash
# Upload
curl -F "file=@/path/to/document.pdf" http://localhost:8000/documents/upload

# Check status (use doc_id from upload response)
curl http://localhost:8000/documents/<doc_id>/status

# Query (after status is completed)
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is this document about?"}'
```

## Scaling workers

To run more Celery workers (e.g. 4):

```bash
docker compose up --build --scale worker=4
```

## Running without Docker

- Install Python 3.11, run PostgreSQL (with pgvector) and Redis locally or in Docker.
- Create a venv, install deps: `pip install -r requirements.txt`.
- Set `.env` with `localhost` for DB and Redis.
- Start API: `uvicorn app.main:app --reload --port 8000`.
- In another terminal, start a worker: `celery -A app.tasks.celery_app worker --loglevel=info`.

## Project structure

```
app/
  api/          # FastAPI routers (documents, health, query)
  models.py     # SQLAlchemy models, engine, AsyncSession
  config.py     # Settings from env
  main.py       # FastAPI app, lifespan (DB init, pgvector extension)
  services/     # Embedder, LLM, cache, chunker, vector_store
  tasks/        # Celery app and ingest task
tests/
docker-compose.yml
Dockerfile
requirements.txt
PRD.md          # Product requirements and design
```
