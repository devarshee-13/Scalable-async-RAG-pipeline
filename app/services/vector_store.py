import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk


@dataclass
class ChunkResult:
    doc_id: uuid.UUID
    chunk_index: int
    text: str
    score: float


async def upsert_chunks(
    session: AsyncSession,
    doc_id: uuid.UUID,
    texts: list[str],
    embeddings: list[list[float]],
) -> None:
    # Delete existing chunks for this doc (re-ingestion support)
    await session.execute(delete(Chunk).where(Chunk.doc_id == doc_id))

    chunks = [
        Chunk(doc_id=doc_id, chunk_index=i, text=text, embedding=embedding)
        for i, (text, embedding) in enumerate(zip(texts, embeddings))
    ]
    session.add_all(chunks)
    await session.commit()


async def search(
    session: AsyncSession,
    query_embedding: list[float],
    doc_id: uuid.UUID | None = None,
    top_k: int = 5,
) -> list[ChunkResult]:
    vec_literal = f"'[{','.join(str(v) for v in query_embedding)}]'::vector"

    if doc_id is not None:
        sql = text(f"""
            SELECT doc_id, chunk_index, text,
                   1 - (embedding <=> {vec_literal}) AS score
            FROM chunks
            WHERE doc_id = :doc_id
            ORDER BY embedding <=> {vec_literal}
            LIMIT :top_k
        """)
        result = await session.execute(sql, {"doc_id": str(doc_id), "top_k": top_k})
    else:
        sql = text(f"""
            SELECT doc_id, chunk_index, text,
                   1 - (embedding <=> {vec_literal}) AS score
            FROM chunks
            ORDER BY embedding <=> {vec_literal}
            LIMIT :top_k
        """)
        result = await session.execute(sql, {"top_k": top_k})

    return [
        ChunkResult(
            doc_id=row.doc_id,
            chunk_index=row.chunk_index,
            text=row.text,
            score=float(row.score),
        )
        for row in result.fetchall()
    ]
