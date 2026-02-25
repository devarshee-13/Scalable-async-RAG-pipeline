import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_upload_txt_returns_202(client):
    resp = await client.post(
        "/documents/upload",
        files={"file": ("sample.txt", b"This is a test document with some content.", "text/plain")},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "doc_id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_upload_invalid_type_returns_422(client):
    resp = await client.post(
        "/documents/upload",
        files={"file": ("image.png", b"\x89PNG\r\n", "image/png")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_status_endpoint_returns_document(client):
    # Upload first
    upload = await client.post(
        "/documents/upload",
        files={"file": ("check.txt", b"Status check content.", "text/plain")},
    )
    doc_id = upload.json()["doc_id"]

    resp = await client.get(f"/documents/{doc_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == doc_id
    assert data["status"] in {"pending", "processing", "completed", "failed"}


@pytest.mark.asyncio
async def test_status_unknown_id_returns_404(client):
    resp = await client.get("/documents/00000000-0000-0000-0000-000000000000/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_query_no_documents_returns_answer(client, monkeypatch):
    # Mock LLM to avoid real API calls
    async def fake_generate(self, query, context_chunks):
        return "No relevant content found."

    monkeypatch.setattr("app.services.llm.LLMClient.generate", fake_generate)
    monkeypatch.setattr("app.services.llm._llm_client", None)

    resp = await client.post("/query", json={"query": "What is the capital of France?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data
    assert "cached" in data
    assert "latency_ms" in data


@pytest.mark.asyncio
async def test_query_cache_hit_on_second_call(client, monkeypatch):
    call_count = 0

    async def counting_generate(self, query, context_chunks):
        nonlocal call_count
        call_count += 1
        return "Cached answer."

    monkeypatch.setattr("app.services.llm.LLMClient.generate", counting_generate)
    monkeypatch.setattr("app.services.llm._llm_client", None)

    query = {"query": "unique test query for cache hit validation xyz"}
    resp1 = await client.post("/query", json=query)
    resp2 = await client.post("/query", json=query)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp2.json()["cached"] is True
    # LLM was only called once despite two requests
    assert call_count == 1
