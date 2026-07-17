from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", case_sensitive=False)

    # Database (Supabase Postgres in production — use the session-pooler URL;
    # local dev uses the docker-compose pgvector container)
    database_url: str = "postgresql://user:password@localhost:5432/civicspark_db"

    # Security
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # External APIs
    openai_api_key: str | None = None
    geocodio_api_key: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    resend_api_key: str | None = None
    from_email: str | None = None

    # Ingestion
    ingest_api_token: str | None = None
    ingest_stale_after_days: int = 7

    # Application
    project_name: str = "CivicSpark AI"
    project_description: str = "CivicSpark AI Backend API"
    project_version: str = "1.0.0"
    api_version: str = "v1"
    environment: str = "development"
    debug: bool = True
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # RAG Configuration
    enable_rag: bool = True
    max_tokens: int = 4000
    temperature: float = 0.7
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    # Agenda items longer than this are split at sentence boundaries
    max_chunk_tokens: int = 1200

    @property
    def is_openai_configured(self) -> bool:
        """Check if OpenAI API key is properly configured"""
        return (
            self.openai_api_key is not None
            and self.openai_api_key.strip() != ""
            and not self.openai_api_key.startswith("sk-placeholder")
        )


settings = Settings()


def get_settings() -> Settings:
    """Get settings instance for dependency injection"""
    return settings
