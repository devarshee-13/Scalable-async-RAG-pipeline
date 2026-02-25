from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    embedder_backend: str = "local"  # "local" | "openai"
    llm_backend: str = "openai"      # "openai" | "ollama"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    ollama_base_url: str = "http://ollama:11434/v1"

    class Config:
        env_file = ".env"


settings = Settings()
