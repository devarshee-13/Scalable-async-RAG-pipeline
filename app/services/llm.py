import openai

from app.config import settings


class LLMClient:
    def __init__(self):
        if settings.llm_backend == "ollama":
            self._client = openai.AsyncOpenAI(
                base_url=settings.ollama_base_url,
                api_key="ollama",
            )
        else:
            self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate(self, query: str, context_chunks: list[str]) -> str:
        context = "\n\n---\n\n".join(context_chunks)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Answer the user's question using ONLY "
                    "the provided context. If the context doesn't contain enough information, "
                    "say so. Do not hallucinate."
                ),
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {query}",
            },
        ]
        response = await self._client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.1,
            max_tokens=512,
        )
        return response.choices[0].message.content or ""


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
