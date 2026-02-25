import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.models import AsyncSession, Document, DocumentStatus

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class DocumentResponse(BaseModel):
    doc_id: str
    filename: str
    status: str
    chunk_count: int


@router.post("/documents/upload", status_code=202, response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {ext!r}. Use PDF or TXT.")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")

    async with AsyncSession() as session:
        doc = Document(filename=filename, status=DocumentStatus.PENDING)
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = str(doc.id)

    r = aioredis.from_url(settings.redis_url)
    await r.setex(f"raw:{doc_id}", 3600, content)
    await r.aclose()

    # Import here to avoid circular import at module load time
    from app.tasks.ingest import ingest_document_task
    ingest_document_task.delay(doc_id)

    return DocumentResponse(
        doc_id=doc_id,
        filename=filename,
        status=DocumentStatus.PENDING,
        chunk_count=0,
    )


@router.get("/documents/{doc_id}/status", response_model=DocumentResponse)
async def get_document_status(doc_id: str):
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id format.")

    async with AsyncSession() as session:
        doc = await session.get(Document, doc_uuid)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")

    return DocumentResponse(
        doc_id=str(doc.id),
        filename=doc.filename,
        status=doc.status.value,
        chunk_count=doc.chunk_count,
    )
