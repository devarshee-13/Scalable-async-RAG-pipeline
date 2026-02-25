from abc import ABC, abstractmethod

from app.config import settings


class BaseEmbedder(ABC):
    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


class SentenceTransformerEmbedder(BaseEmbedder):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, batch_size=32, normalize_embeddings=True)
        return vectors.tolist()


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self):
        import openai
        self._client = openai.OpenAI(api_key=settings.openai_api_key)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model="text-embedding-3-small", input=texts
        )
        return [item.embedding for item in response.data]


_embedder: BaseEmbedder | None = None


def get_embedder() -> BaseEmbedder:
    global _embedder
    if _embedder is None:
        if settings.embedder_backend == "openai":
            _embedder = OpenAIEmbedder()
        else:
            _embedder = SentenceTransformerEmbedder()
    return _embedder
