import logging
import warnings
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

DEFAULT_SECRET_KEY = "your-secret-key-here"  # nosec B105 - dev placeholder

# Origins allowed by default during local development.
DEV_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3007",
    "http://localhost:5173",
    "http://127.0.0.1:3007",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

    # Database — the single stateful service in the architecture.
    # Postgres holds relational data AND the RAG vector index (pgvector).
    database_url: str = "postgresql://user:password@localhost:5435/citycamp_db"

    # Security
    secret_key: str = DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # External APIs (all optional — features degrade gracefully without them)
    openai_api_key: Optional[str] = None
    geocodio_api_key: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None

    # Google Custom Search API (optional web-research capability)
    google_api_key: Optional[str] = None
    google_cse_id: Optional[str] = None

    # File storage: local disk by default; set to "s3" only if AWS is configured
    storage_backend: str = "local"
    storage_dir: str = "./storage"
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_s3_bucket: str = "citycamp-assets"

    # City Data Sources
    tulsa_city_council_api_url: str = "https://api.tulsacouncil.org"
    tulsa_city_council_api_key: Optional[str] = None

    # Email
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_tls: bool = True
    smtp_ssl: bool = False
    from_email: Optional[str] = None

    # Application
    project_name: str = "CivicSpark AI"
    project_description: str = "CivicSpark AI Backend API"
    project_version: str = "2.0.0"
    api_version: str = "v1"
    environment: str = "development"
    debug: bool = True

    # Comma-separated list, e.g. "https://civicspark.vercel.app,https://civicspark.org"
    cors_origins: str = ""

    # RAG Configuration
    enable_rag: bool = True
    max_tokens: int = 4000
    temperature: float = 0.7
    chunk_size: int = 1000
    chunk_overlap: int = 200

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> List[str]:
        """Resolved CORS origins.

        Explicit origins from the CORS_ORIGINS env var always win. Without
        them, development allows common local dev servers; production allows
        nothing cross-origin (same-origin requests via the Vercel /api rewrite
        don't need CORS at all).
        """
        configured = [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]
        if configured:
            return configured
        if self.is_production:
            return []
        return DEV_CORS_ORIGINS

    @property
    def is_openai_configured(self) -> bool:
        """Check if OpenAI API key is properly configured"""
        return (
            self.openai_api_key is not None
            and self.openai_api_key.strip() != ""
            and not self.openai_api_key.startswith("sk-placeholder")
        )

    def validate_production_settings(self) -> None:
        """Fail fast on unsafe production configuration"""
        if not self.is_production:
            return
        if self.secret_key == DEFAULT_SECRET_KEY or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY must be set to a strong value (32+ chars) in production"
            )
        if self.debug:
            warnings.warn("DEBUG should be disabled in production", stacklevel=1)


settings = Settings()


def get_settings() -> Settings:
    """Get settings instance for dependency injection"""
    return settings
