from app.services.chunker import DocumentChunker


def test_short_text_returns_single_chunk():
    chunker = DocumentChunker(chunk_size=512, chunk_overlap=64)
    chunks = chunker.chunk("Hello world")
    assert len(chunks) == 1
    assert chunks[0].text == "Hello world"
    assert chunks[0].index == 0


def test_long_text_respects_chunk_size():
    chunker = DocumentChunker(chunk_size=100, chunk_overlap=0)
    text = "a" * 250
    chunks = chunker.chunk(text)
    assert len(chunks) == 3
    for chunk in chunks:
        assert len(chunk.text) <= 100


def test_overlap_produces_repeated_content():
    chunker = DocumentChunker(chunk_size=10, chunk_overlap=5)
    text = "abcdefghijklmnopqrst"  # 20 chars
    chunks = chunker.chunk(text)
    assert len(chunks) >= 2
    # Second chunk starts 5 chars into the first chunk's territory
    assert chunks[1].text[:5] == chunks[0].text[5:10]


def test_empty_text_returns_no_chunks():
    chunker = DocumentChunker()
    chunks = chunker.chunk("   ")
    assert chunks == []


def test_chunk_indices_are_sequential():
    chunker = DocumentChunker(chunk_size=50, chunk_overlap=0)
    text = "word " * 100
    chunks = chunker.chunk(text)
    for i, chunk in enumerate(chunks):
        assert chunk.index == i
