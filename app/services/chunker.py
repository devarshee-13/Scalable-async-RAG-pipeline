from dataclasses import dataclass


@dataclass
class ChunkData:
    text: str
    index: int


class DocumentChunker:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> list[ChunkData]:
        chunks = []
        start = 0
        index = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(ChunkData(text=chunk_text, index=index))
                index += 1
            start += self.chunk_size - self.chunk_overlap
        return chunks
