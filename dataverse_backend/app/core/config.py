"""Configuration management for DataVerse AI.

Uses environment variables for all configurable parameters to ensure 12-factor principles.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DataVerse AI"
    ENVIRONMENT: str = Field(default="development")
    APP_VERSION: str = Field(default="1.0.0")
    ENABLE_OPENAPI_DOCS: bool = Field(default=True)
    REQUEST_TIMEOUT_SECONDS: int = Field(default=60)

    # Logging
    LOG_DIR: str = Field(default="./logs")
    LOG_LEVEL: str = Field(default="INFO")
    LOG_JSON: bool = Field(default=False)

    # API and transport security
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    )
    TRUSTED_HOSTS: str = Field(default="localhost,127.0.0.1,testserver")
    SECURE_HEADERS_ENABLED: bool = Field(default=True)
    HTTPS_REDIRECT: bool = Field(default=False)

    # API rate limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_REQUESTS: int = Field(default=120)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)
    RATE_LIMIT_PATH_PREFIX: str = Field(default="/api")

    # Intent parsing provider
    # Options: "auto" (default), "deepseek", "openai"
    INTENT_LLM_PROVIDER: str = Field(default="auto")
    INTENT_LLM_TIMEOUT: int = Field(default=20)

    # OpenAI for intent parsing
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    OPENAI_API_BASE: Optional[str] = Field(default=None)
    OPENAI_CHAT_MODEL: str = Field(default="gpt-4o")
    OPENAI_INTENT_MODEL: str = Field(default="gpt-4o-mini")

    # DeepSeek for intent parsing (OpenAI-compatible API)
    DEEPSEEK_API_KEY: Optional[str] = Field(default=None)
    DEEPSEEK_API_BASE: str = Field(default="https://api.deepseek.com")
    DEEPSEEK_INTENT_MODEL: str = Field(default="deepseek-chat")

    # DeepAnalyze / Ollama settings
    DEEPANALYZE_BASE_URL: str = Field(default="http://localhost:11434")
    # Preferred logical role/model used for reasoning. This is the primary model name the system will
    # attempt to use, but the system treats this as a logical role and will fall back to other local
    # models if allowed by configuration. This prevents crashes when a specific model artifact is missing.
    DEEPANALYZE_MODEL: str = Field(default="deepanalyze-8b")
    # A reasonable default fallback model installed locally via Ollama (phi3:mini is available offline)
    DEEPANALYZE_FALLBACK_MODEL: str = Field(default="phi3:mini")
    DEEPANALYZE_TIMEOUT: int = Field(default=20)
    # Allow falling back to local models when the preferred model isn't available. Safe for dev.
    DEEPANALYZE_ALLOW_FALLBACK: bool = Field(default=True)

    # Mistral for budget-conscious task routing and lightweight chat
    MISTRAL_API_KEY: Optional[str] = Field(default=None)
    MISTRAL_API_BASE: str = Field(default="https://api.mistral.ai/v1")
    MISTRAL_CHAT_MODEL: str = Field(default="mistral-small-latest")
    MISTRAL_REASONING_MODEL: str = Field(default="mistral-large-latest")

    # Security / Limits
    MAX_UPLOAD_SIZE_MB: int = Field(default=50)

    # Authentication
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production")
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)

    # Database
    # Expect a full async SQLAlchemy-compatible DATABASE_URL, e.g.
    # postgresql+asyncpg://user:password@host:5432/dbname
    DATABASE_URL: str | None = Field(default=None)
    DATABASE_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0)

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_CONNECT_TIMEOUT_SECONDS: float = Field(default=1.0)

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")

    # File Storage
    STORAGE_TYPE: str = Field(default="local")  # local, minio, s3

    # MinIO Configuration
    MINIO_ENDPOINT: str = Field(default="localhost:9000")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin")
    MINIO_SECRET_KEY: str = Field(default="minioadmin")
    MINIO_BUCKET: str = Field(default="dataverse")
    MINIO_SECURE: bool = Field(default=False)

    # AWS S3 Configuration
    AWS_REGION: str = Field(default="us-east-1")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None)
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None)
    AWS_S3_BUCKET: str = Field(default="dataverse")

    # Claude AI
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None)
    CLAUDE_MODEL: str = Field(default="claude-3-5-sonnet-20241022")

    # Stripe billing
    STRIPE_SECRET_KEY: Optional[str] = Field(default=None)
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(default=None)
    STRIPE_PRICE_PRO_MONTHLY: Optional[str] = Field(default=None)
    STRIPE_PRICE_TEAM_MONTHLY: Optional[str] = Field(default=None)
    APP_BASE_URL: str = Field(default="http://localhost:3000")

    # Sentry
    SENTRY_DSN: Optional[str] = Field(default=None)
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.1)
    SENTRY_PROFILES_SAMPLE_RATE: float = Field(default=0.0)

    model_config = SettingsConfigDict(
        env_file=str((Path(__file__).resolve().parents[2] / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def trusted_hosts_list(self) -> List[str]:
        return [host.strip() for host in self.TRUSTED_HOSTS.split(",") if host.strip()]


settings = Settings()
