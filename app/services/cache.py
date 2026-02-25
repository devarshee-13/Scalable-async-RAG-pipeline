import hashlib
import json

import redis.asyncio as aioredis

from app.config import settings

TTL = 3600  # 1 hour


def _make_key(query: str, doc_id: str | None) -> str:
    payload = {"q": query.lower().strip(), "doc_id": doc_id or ""}
    return "rag:query:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def cache_get(query: str, doc_id: str | None) -> dict | None:
    r = aioredis.from_url(settings.redis_url)
    try:
        raw = await r.get(_make_key(query, doc_id))
        return json.loads(raw) if raw else None
    finally:
        await r.aclose()


async def cache_set(query: str, doc_id: str | None, result: dict) -> None:
    r = aioredis.from_url(settings.redis_url)
    try:
        await r.setex(_make_key(query, doc_id), TTL, json.dumps(result))
    finally:
        await r.aclose()
