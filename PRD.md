# Product Requirements Document
## Scalable Async RAG Pipeline

**Version:** 1.0
**Date:** 2026-02-25
**Status:** In Development

---

## 1. Overview

### Problem Statement

Developers building internal knowledge tools, document Q&A systems, or research assistants need a backend capable of ingesting large volumes of documents and answering natural-language queries against them in near-real-time. Naive implementations (synchronous processing, no caching, full-table vector scans) fail under load — uploads block the API thread, query latency degrades as the corpus grows, and there is no visibility into system health.

### Solution

A production-ready, async document ingestion and retrieval-augmented generation (RAG) API that decouples uploads from processing, uses approximate nearest-neighbor (ANN) vector search for sub-10ms retrieval, caches query results in Redis, and exposes Prometheus metrics for observability.

### Target Users

| User | Need |
|---|---|
| Internal tooling teams | Drop-in backend for document Q&A features |
| ML engineers | Reference architecture for async RAG pipelines |
| Recruiters / interviewers | Demonstration of systems + AI application skills |

---

## 2. Goals

### Primary Goals
1. Accept PDF and plain-text documents via HTTP and process them asynchronously without blocking the API
2. Answer natural-language queries against the ingested corpus with source citations
3. Scale ingestion throughput horizontally by adding worker replicas
4. Achieve measurable latency reduction via query result caching

### Non-Goals
- User authentication / authorization (API is open by design for demo purposes)
- A frontend / UI
- Multi-tenancy or per-user document isolation
- Streaming / server-sent events for answer generation
- Production deployment (Kubernetes, Terraform, managed cloud services)

---

## 3. Success Metrics

| Metric | Target |
|---|---|
| Ingestion throughput | ≥ 450 chunks/sec (1 worker, `all-MiniLM-L6-v2`) |
| ANN search latency | < 10 ms across 50K chunks |
| Query cache hit rate | ≥ 70% on repeated-query workloads |
| p95 cached query latency | < 200 ms |
| p95 uncached query latency | < 3.5 s (network-bound by LLM call) |
| Worker scale-out speedup | ~3x on 4 workers vs 1 worker (100-doc batch) |
| CI success rate | 100% on every PR (lint + tests pass) |

---

## 4. User Stories

### Document Ingestion
- **As a developer**, I want to `POST /documents/upload` with a PDF or TXT file and receive a `202 Accepted` response immediately, so my HTTP client is never blocked waiting for processing.
- **As a developer**, I want to `GET /documents/{id}/status` to poll the processing state (`pending → processing → completed | failed`), so I know when a document is queryable.
- **As a developer**, I want upload failures to be retried automatically (up to 3 times), so transient errors (Redis timeout, DB hiccup) don't silently drop documents.

### Querying
- **As a developer**, I want to `POST /query` with a natural-language question and an optional `doc_id` filter, and receive an answer grounded in the document corpus with source citations (doc ID, chunk index, similarity score).
- **As a developer**, I want identical queries to return from cache with latency < 200 ms, so the system is cost-efficient under repeated-query workloads.
- **As a developer**, I want the response to include a `cached: true | false` flag and `latency_ms`, so I can observe caching behavior directly from the API response.

### Operations
- **As a developer**, I want `GET /health` to confirm the API is alive.
- **As a developer**, I want `GET /metrics` to expose Prometheus metrics, so I can monitor ingestion throughput, query latency, cache hit rate, and vector search performance.
- **As a developer**, I want to scale workers with `docker compose up --scale worker=N`, so I can demonstrate horizontal scale-out without infrastructure changes.

---

## 5. Functional Requirements

### 5.1 Document Upload (`POST /documents/upload`)

| # | Requirement |
|---|---|
| F-1 | Accept `multipart/form-data` with a single file field |
| F-2 | Reject files with extensions other than `.pdf` and `.txt` with HTTP 422 |
| F-3 | Reject files larger than 10 MB with HTTP 413 |
| F-4 | Create a `Document` record in the database with status `pending` |
| F-5 | Store raw file bytes in Redis with a 1-hour TTL |
| F-6 | Enqueue an ingestion task on the Celery queue |
| F-7 | Return HTTP 202 with `{doc_id, filename, status, chunk_count}` |

### 5.2 Document Status (`GET /documents/{doc_id}/status`)

| # | Requirement |
|---|---|
| F-8 | Return the current document status and chunk count |
| F-9 | Return HTTP 404 if `doc_id` is not found |
| F-10 | Return HTTP 422 if `doc_id` is not a valid UUID |

### 5.3 Ingestion Worker

| # | Requirement |
|---|---|
| F-11 | Set document status to `processing` before starting work |
| F-12 | Parse PDF files with PyMuPDF; parse TXT files as UTF-8 |
| F-13 | Split document text into chunks of ≤ 512 characters with 64-character overlap |
| F-14 | Embed chunks using `all-MiniLM-L6-v2` (384 dims) in batches of 32 |
| F-15 | Upsert all chunks (text + embedding) to the `chunks` table |
| F-16 | Set document status to `completed` and record `chunk_count` on success |
| F-17 | Set document status to `failed` and record `error_msg` on unrecoverable failure |
| F-18 | Retry failed tasks up to 3 times with a 60-second delay |
| F-19 | Delete the raw file from Redis after successful ingestion |
| F-20 | Support re-ingestion: delete existing chunks before inserting new ones |

### 5.4 Query (`POST /query`)

| # | Requirement |
|---|---|
| F-21 | Accept `{query: string, doc_id?: string, top_k?: int}` as JSON body |
| F-22 | Validate `query` length: 3–1000 characters |
| F-23 | Validate `top_k`: 1–20, default 5 |
| F-24 | Check Redis cache before any embedding or LLM call |
| F-25 | Embed the query using the same model as ingestion |
| F-26 | Perform ANN search via HNSW index using cosine distance |
| F-27 | Filter results by `doc_id` when provided |
| F-28 | Pass top-K retrieved chunks as context to the LLM |
| F-29 | Constrain the LLM via system prompt to answer only from provided context |
| F-30 | Return `{answer, sources: [{doc_id, chunk_index, score}], cached, latency_ms}` |
| F-31 | Cache the result in Redis with a 1-hour TTL |
| F-32 | Return `"No relevant documents found."` when the corpus is empty |

### 5.5 Observability

| # | Metric | Type | Instrumented In |
|---|---|---|---|
| F-33 | `rag_chunks_embedded_total` | Counter | Ingest task |
| F-34 | `rag_embed_duration_seconds` | Histogram | Ingest task |
| F-35 | `rag_query_latency_seconds` | Histogram | Query endpoint |
| F-36 | `rag_cache_hits_total` | Counter | Query endpoint |
| F-37 | `rag_vector_search_seconds` | Histogram | Query endpoint |

---

## 6. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Availability** | API remains responsive under concurrent upload and query load |
| **Scalability** | Ingestion workers scale horizontally via `--scale worker=N` with no code changes |
| **Durability** | Tasks with `acks_late=True` are not lost if a worker crashes mid-ingestion |
| **Correctness** | Cosine similarity search returns the semantically closest chunks, not random results |
| **Portability** | Full stack runs on any machine with Docker Compose via a single `docker compose up` |
| **Maintainability** | Ruff lint enforced on every PR; no type errors in the hot path |
| **Security** | LLM answers constrained to provided context (temperature 0.1, explicit system prompt) |

---

## 7. Architecture

### Tech Stack

| Layer | Technology | Role |
|---|---|---|
| API | FastAPI + Uvicorn | Async HTTP server, request validation, routing |
| Task queue | Celery 5 | Background ingestion; `acks_late=True` for crash safety |
| Broker / Cache | Redis 7 | Celery broker (DB 0), query result cache (DB 0), raw file buffer (DB 0) |
| Result backend | Redis 7 (DB 1) | Celery task result storage |
| Database | PostgreSQL 16 + pgvector | Document metadata + 384-dim vector storage |
| Vector index | HNSW (m=16, ef_construction=64) | Sub-10ms approximate nearest-neighbor search |
| Embedder | sentence-transformers `all-MiniLM-L6-v2` | 384-dim text embeddings (local, no API key) |
| LLM | Ollama (`llama3.2`) or OpenAI (`gpt-4o-mini`) | Context-constrained answer generation |
| Observability | prometheus-client | 5 metrics at `GET /metrics` |
| CI | GitHub Actions | Ruff lint + pytest on every PR and push to `main` |
| Packaging | Docker Compose | Single-command local stack (`docker compose up`) |

### Component Diagram

```
Client (curl / app)
        │
        │  HTTP :8000
        ▼
┌─────────────────────────────────────────────────┐
│  FastAPI + Uvicorn                              │
│                                                 │
│  POST /documents/upload                         │
│  GET  /documents/{doc_id}/status                │
│  POST /query                                    │
│  GET  /health                                   │
│  GET  /metrics  (Prometheus)                    │
└──────────┬────────────────────┬─────────────────┘
           │                    │
   store raw bytes         asyncpg (SQL)
   SETEX raw:{id}               │
           │                    ▼
           │         ┌──────────────────────┐
           │         │  PostgreSQL 16        │
           │         │  + pgvector           │
           ▼         │                      │
    ┌────────────┐   │  documents           │
    │  Redis 7   │   │  chunks (Vector 384) │
    │            │   │  HNSW index          │
    │  DB 0:     │   └──────────┬───────────┘
    │  broker    │              │ upsert / search
    │  raw buf   │              │
    │  cache     │   ┌──────────┴───────────┐
    │            │   │  Celery Worker(s)    │
    │  DB 1:     │◄──│  ingest_document     │
    │  results   │   │  _task               │
    └────────────┘   │                      │
                     │  PDF/TXT parse       │
                     │  chunk (512 / 64)    │
                     │  embed (batch=32)    │
                     └──────────────────────┘
                                │
                     ┌──────────┴───────────┐
                     │  Embedder            │
                     │  all-MiniLM-L6-v2   │
                     │  (or OpenAI API)     │
                     └──────────────────────┘

                     ┌──────────────────────┐
                     │  LLM                 │
                     │  Ollama (llama3.2)   │
                     │  or OpenAI API       │
                     └──────────────────────┘
```

### Ingestion Pipeline

```
Step 1  Client sends  POST /documents/upload  (multipart, PDF or TXT, ≤ 10 MB)
         │
Step 2  FastAPI validates filetype (.pdf / .txt) and size
         │  fail → HTTP 422 / 413
         │
Step 3  INSERT Document row into PostgreSQL  (status = pending)
         │
Step 4  SETEX raw:{doc_id} → Redis  (raw file bytes, TTL = 1 h)
         │
Step 5  Enqueue ingest_document_task on Celery → return HTTP 202 {doc_id}
         │
         ╔══════════════════════════════════════════╗
         ║         Celery Worker (async)            ║
Step 6  ║  UPDATE Document status = processing     ║
         ║  GET raw:{doc_id} from Redis             ║
         ║  Parse: PyMuPDF (PDF) | UTF-8 (TXT)     ║
         ║                                          ║
Step 7  ║  Chunk text  →  512-char / 64 overlap    ║
         ║  Embed chunks in batches of 32           ║
         ║   → all-MiniLM-L6-v2  (384 dims)        ║
         ║  DELETE old chunks  (re-ingestion safe)  ║
         ║  INSERT chunks (text + embedding)        ║
         ║                                          ║
         ║  success → status = completed            ║
         ║  failure → status = failed, error_msg    ║
         ║            retry × 3, delay = 60 s       ║
         ║  DEL raw:{doc_id} from Redis             ║
         ╚══════════════════════════════════════════╝
```

### Query Pipeline

```
Step 1  Client sends  POST /query  {query, doc_id?, top_k}
         │  validate: query 3–1000 chars, top_k 1–20
         │
Step 2  Compute cache key  SHA-256(query.lower() + doc_id)
         GET key from Redis
         │  HIT  → return {answer, sources, cached: true, latency_ms}
         │
Step 3  CACHE MISS — embed query string
         all-MiniLM-L6-v2  →  384-dim vector
         │
Step 4  ANN search via HNSW index (cosine distance)
         SELECT … ORDER BY embedding <=> qvec LIMIT top_k
         optional WHERE doc_id = ?
         → top-K ChunkResult (doc_id, chunk_index, text, score)
         │  empty corpus → return "No relevant documents found."
         │
Step 5  LLM generation
         system prompt: "Answer ONLY from provided context. Do not hallucinate."
         user prompt:   context chunks + question
         model: Ollama llama3.2  (or OpenAI gpt-4o-mini)
         temperature: 0.1 | max_tokens: 512
         │
Step 6  SETEX cache key → Redis  (TTL = 1 h)
         return {answer, sources: [{doc_id, chunk_index, score}],
                 cached: false, latency_ms}
```

### Database Schema

```sql
CREATE TABLE documents (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filename    VARCHAR(512) NOT NULL,
  status      document_status NOT NULL DEFAULT 'pending',
  chunk_count INTEGER DEFAULT 0,
  error_msg   VARCHAR(1024),
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chunks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id      UUID REFERENCES documents(id),
  chunk_index INTEGER NOT NULL,
  text        TEXT NOT NULL,
  embedding   VECTOR(384) NOT NULL
);

CREATE INDEX chunks_embedding_hnsw_idx
  ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

---

## 8. API Reference

### `POST /documents/upload`
**Content-Type:** `multipart/form-data`

**Request:** file field (PDF or TXT, max 10 MB)

**Response 202:**
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "report.pdf",
  "status": "pending",
  "chunk_count": 0
}
```

**Errors:** 422 (bad filetype), 413 (too large)

---

### `GET /documents/{doc_id}/status`

**Response 200:**
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "report.pdf",
  "status": "completed",
  "chunk_count": 47
}
```

**Status values:** `pending` | `processing` | `completed` | `failed`
**Errors:** 404 (not found), 422 (invalid UUID)

---

### `POST /query`
**Content-Type:** `application/json`

**Request:**
```json
{
  "query": "What are the main conclusions?",
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "top_k": 5
}
```

**Response 200:**
```json
{
  "answer": "The main conclusions are...",
  "sources": [
    {"doc_id": "550e8400-...", "chunk_index": 12, "score": 0.91},
    {"doc_id": "550e8400-...", "chunk_index": 8,  "score": 0.87}
  ],
  "cached": false,
  "latency_ms": 1243.7
}
```

---

### `GET /health`
```json
{"status": "ok"}
```

### `GET /metrics`
Prometheus text exposition format (counters, histograms).

---

## 9. Configuration

All settings are read from environment variables (`.env` file in development):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://rag:rag@postgres:5432/rag` | Async PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | Celery result store |
| `EMBEDDER_BACKEND` | `local` | `local` (sentence-transformers) or `openai` |
| `LLM_BACKEND` | `ollama` | `ollama` or `openai` |
| `LLM_MODEL` | `llama3.2` | Model name passed to LLM API |
| `OPENAI_API_KEY` | _(required only if `LLM_BACKEND=openai`)_ | OpenAI API key |
| `OLLAMA_BASE_URL` | `http://ollama:11434/v1` | Ollama OpenAI-compatible base URL |

### Recommended Setup

**Option A — Local / Free (recommended for development)**
```env
EMBEDDER_BACKEND=local
LLM_BACKEND=ollama
LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://ollama:11434/v1
```

**Option B — Cloud / OpenAI**
```env
EMBEDDER_BACKEND=local
LLM_BACKEND=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

---

## 10. Known Limitations & Future Work

| Limitation | Impact | Potential Fix |
|---|---|---|
| No authentication | Any caller can upload or query | Add API key middleware |
| Redis connection-per-call in `cache.py` | Minor overhead at high QPS | Use a shared `aioredis.ConnectionPool` |
| Fixed chunk size / overlap (not configurable per upload) | One-size-fits-all chunking | Accept `chunk_size` as an upload parameter |
| Basic PDF text extraction (no OCR, no table parsing) | Scanned PDFs return empty text | Integrate `tesseract` or `unstructured` |
| Single embedding model (384 dims, hardcoded) | Can't mix models across documents | Store model name per document; re-embed on query |
| Fixed retry delay (60s flat, no exponential backoff) | Slow recovery from transient failures | Implement `countdown = 60 * 2 ** self.request.retries` |
| No document deletion endpoint | Re-ingestion requires direct DB access | Add `DELETE /documents/{id}` |
| LLM max_tokens=512 | Long answers are truncated | Make configurable or use token counting |

---

## 11. Verification Checklist

```
[ ] docker compose up  →  all 4 services healthy
[ ] curl -X POST /documents/upload -F "file=@sample.pdf"  →  202 + doc_id
[ ] Poll GET /documents/{id}/status  →  transitions through pending → processing → completed
[ ] curl -X POST /query '{"query": "..."}'  →  {answer, sources, cached: false}
[ ] Repeat same query  →  {cached: true, latency_ms < 200}
[ ] docker compose up --scale worker=4  →  ingest 20 docs, compare wall-clock time vs 1 worker
[ ] curl localhost:8000/metrics  →  rag_* counters and histograms present
[ ] pytest tests/  →  all 13 tests pass
[ ] ruff check .  →  no lint errors
[ ] Push PR  →  CI workflow green on GitHub Actions
```
