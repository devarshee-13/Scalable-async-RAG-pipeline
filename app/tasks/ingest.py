import asyncio
import time
import uuid

import redis as sync_redis
from prometheus_client import Counter, Histogram

from app.config import settings
from app.models import AsyncSession, Document, DocumentStatus
from app.services.chunker import DocumentChunker
from app.services.embedder import get_embedder
from app.services.vector_store import upsert_chunks
from app.tasks.celery_app import celery_app

CHUNKS_EMBEDDED_TOTAL = Counter(
    "rag_chunks_embedded_total", "Total chunks embedded and stored"
)
EMBED_DURATION_SECONDS = Histogram(
    "rag_embed_duration_seconds",
    "Time spent embedding chunks",
    buckets=[0.1, 0.5, 1, 2, 5, 10],
)

_chunker = DocumentChunker()
_redis = sync_redis.from_url(settings.redis_url)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document_task(self, doc_id: str) -> dict:
    return asyncio.run(_ingest(self, doc_id))


async def _ingest(task, doc_id: str) -> dict:
    doc_uuid = uuid.UUID(doc_id)

    async with AsyncSession() as session:
        doc = await session.get(Document, doc_uuid)
        if doc is None:
            return {"error": "document not found"}

        doc.status = DocumentStatus.PROCESSING
        await session.commit()

        try:
            raw = _redis.get(f"raw:{doc_id}")
            if raw is None:
                raise ValueError("raw file not found in Redis")

            # Parse
            filename = doc.filename.lower()
            if filename.endswith(".pdf"):
                import fitz
                pdf = fitz.open(stream=raw, filetype="pdf")
                text = "\n".join(page.get_text() for page in pdf)
            else:
                text = raw.decode("utf-8", errors="replace")

            # Chunk
            chunks = _chunker.chunk(text)
            if not chunks:
                raise ValueError("no chunks produced from document")

            # Embed in batches of 32
            embedder = get_embedder()
            texts = [c.text for c in chunks]
            all_embeddings: list[list[float]] = []
            t_embed = time.monotonic()
            for i in range(0, len(texts), 32):
                batch = texts[i : i + 32]
                all_embeddings.extend(embedder.embed_batch(batch))
            EMBED_DURATION_SECONDS.observe(time.monotonic() - t_embed)
            CHUNKS_EMBEDDED_TOTAL.inc(len(texts))

            # Upsert
            await upsert_chunks(session, doc_uuid, texts, all_embeddings)

            doc.status = DocumentStatus.COMPLETED
            doc.chunk_count = len(chunks)
            await session.commit()

            _redis.delete(f"raw:{doc_id}")
            return {"doc_id": doc_id, "chunk_count": len(chunks)}

        except Exception as exc:
            doc.status = DocumentStatus.FAILED
            doc.error_msg = str(exc)[:1024]
            await session.commit()
            raise task.retry(exc=exc)
