import time
import uuid

from fastapi import APIRouter, HTTPException
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field

from app.models import AsyncSession
from app.services.cache import cache_get, cache_set
from app.services.embedder import get_embedder
from app.services.llm import get_llm_client
from app.services.vector_store import search

QUERY_LATENCY_SECONDS = Histogram(
    "rag_query_latency_seconds",
    "End-to-end query latency",
    buckets=[0.1, 0.5, 1, 2, 5, 10],
)
CACHE_HITS_TOTAL = Counter("rag_cache_hits_total", "Query cache hits")
VECTOR_SEARCH_SECONDS = Histogram(
    "rag_vector_search_seconds",
    "pgvector ANN search latency",
    buckets=[0.01, 0.05, 0.1, 0.5, 1],
)

router = APIRouter()


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    doc_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SourceCitation(BaseModel):
    doc_id: str
    chunk_index: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceCitation]
    cached: bool
    latency_ms: float


@router.post("/query", response_model=QueryResponse)
async def query_documents(body: QueryRequest):
    t0 = time.monotonic()

    doc_uuid: uuid.UUID | None = None
    if body.doc_id:
        try:
            doc_uuid = uuid.UUID(body.doc_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid doc_id format.")

    # Cache check
    cached = await cache_get(body.query, body.doc_id)
    if cached:
        CACHE_HITS_TOTAL.inc()
        cached["cached"] = True
        cached["latency_ms"] = round((time.monotonic() - t0) * 1000, 2)
        QUERY_LATENCY_SECONDS.observe(time.monotonic() - t0)
        return QueryResponse(**cached)

    # Embed query
    embedder = get_embedder()
    query_vec = embedder.embed_batch([body.query])[0]

    # ANN search
    t_search = time.monotonic()
    async with AsyncSession() as session:
        chunks = await search(session, query_vec, doc_uuid, top_k=body.top_k)
    VECTOR_SEARCH_SECONDS.observe(time.monotonic() - t_search)

    if not chunks:
        return QueryResponse(
            answer="No relevant documents found.",
            sources=[],
            cached=False,
            latency_ms=round((time.monotonic() - t0) * 1000, 2),
        )

    # LLM generation
    llm = get_llm_client()
    answer = await llm.generate(body.query, [c.text for c in chunks])

    sources = [
        SourceCitation(doc_id=str(c.doc_id), chunk_index=c.chunk_index, score=c.score)
        for c in chunks
    ]
    latency_ms = round((time.monotonic() - t0) * 1000, 2)

    result = {
        "answer": answer,
        "sources": [s.model_dump() for s in sources],
        "cached": False,
        "latency_ms": latency_ms,
    }

    QUERY_LATENCY_SECONDS.observe(time.monotonic() - t0)
    await cache_set(body.query, body.doc_id, result)
    return QueryResponse(**result)
