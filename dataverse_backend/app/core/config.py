"""Configuration management for DataVerse AI.

Uses environment variables for all configurable parameters to ensure 12-factor principles.
"""
from __future__ import annotations

import os
from typing import List, Optional
# Support both pydantic v1 and v2 migration where BaseSettings moved to pydantic-settings
try:
    # pydantic v2
    from pydantic_settings import BaseSettings
    from pydantic import Field
except Exception:
    # pydantic v1
    from pydantic import BaseSettings, Field

from pydantic import validator


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DataVerse AI"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    APP_VERSION: str = Field(default="1.0.0", env="APP_VERSION")
    ENABLE_OPENAPI_DOCS: bool = Field(default=True, env="ENABLE_OPENAPI_DOCS")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=60, env="REQUEST_TIMEOUT_SECONDS")

    # Logging
    LOG_DIR: str = Field(default="./logs", env="LOG_DIR")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_JSON: bool = Field(default=False, env="LOG_JSON")

    # API and transport security
    CORS_ORIGINS: str = Field(default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001", env="CORS_ORIGINS")
    TRUSTED_HOSTS: str = Field(default="localhost,127.0.0.1,testserver", env="TRUSTED_HOSTS")
    SECURE_HEADERS_ENABLED: bool = Field(default=True, env="SECURE_HEADERS_ENABLED")
    HTTPS_REDIRECT: bool = Field(default=False, env="HTTPS_REDIRECT")

    # API rate limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_REQUESTS: int = Field(default=120, env="RATE_LIMIT_REQUESTS")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, env="RATE_LIMIT_WINDOW_SECONDS")
    RATE_LIMIT_PATH_PREFIX: str = Field(default="/api", env="RATE_LIMIT_PATH_PREFIX")

    # Intent parsing provider
    # Options: "auto" (default), "deepseek", "openai"
    INTENT_LLM_PROVIDER: str = Field(default="auto", env="INTENT_LLM_PROVIDER")
    INTENT_LLM_TIMEOUT: int = Field(default=20, env="INTENT_LLM_TIMEOUT")

    # OpenAI for intent parsing
<<<<<<< HEAD
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    OPENAI_API_BASE: Optional[str] = Field(default=None, env="OPENAI_API_BASE")
    OPENAI_CHAT_MODEL: str = Field(default="gpt-5.4", env="OPENAI_CHAT_MODEL")
    OPENAI_INTENT_MODEL: str = Field(default="gpt-5-mini", env="OPENAI_INTENT_MODEL")
=======
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    OPENAI_API_BASE: Optional[str] = Field(default=None)
    OPENAI_CHAT_MODEL: str = Field(default="gpt-4o-mini")
    OPENAI_INTENT_MODEL: str = Field(default="gpt-4o-mini")

    # Gemini for report narration fallback after OpenAI
    GEMINI_API_KEY: Optional[str] = Field(default=None)
    GEMINI_API_BASE: str = Field(default="https://generativelanguage.googleapis.com")
    GEMINI_MODEL: str = Field(default="gemini-1.5-flash")
    GEMINI_REPORT_MODEL: str = Field(default="gemini-1.5-pro")

    # Supabase persistence for ChatGPT-style sessions, datasets, agent runs, and reports.
    SUPABASE_URL: Optional[str] = Field(default=None)
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = Field(default=None)
    SUPABASE_ANON_KEY: Optional[str] = Field(default=None)
    SUPABASE_DATASET_BUCKET: str = Field(default="dataverse-datasets")
    SUPABASE_REPORT_BUCKET: str = Field(default="dataverse-reports")
    BACKEND_BASE_URL: str = Field(default="http://localhost:8000")
>>>>>>> 15b8a6d8 (new1)

    # DeepSeek for intent parsing (OpenAI-compatible API)
    DEEPSEEK_API_KEY: Optional[str] = Field(default=None, env="DEEPSEEK_API_KEY")
    DEEPSEEK_API_BASE: str = Field(default="https://api.deepseek.com", env="DEEPSEEK_API_BASE")
    DEEPSEEK_INTENT_MODEL: str = Field(default="deepseek-chat", env="DEEPSEEK_INTENT_MODEL")

    # DeepAnalyze / Ollama settings
<<<<<<< HEAD
    DEEPANALYZE_BASE_URL: str = Field(default="http://localhost:11434", env="DEEPANALYZE_BASE_URL")
=======
    DEEPANALYZE_API_KEY: Optional[str] = Field(default=None)
    DEEPANALYZE_API_BASE: Optional[str] = Field(default=None)
    DEEPANALYZE_LOCAL_BASE_URL: Optional[str] = Field(default=None)
    DEEPANALYZE_BASE_URL: str = Field(default="http://localhost:11434")
>>>>>>> 15b8a6d8 (new1)
    # Preferred logical role/model used for reasoning. This is the primary model name the system will
    # attempt to use, but the system treats this as a logical role and will fall back to other local
    # models if allowed by configuration. This prevents crashes when a specific model artifact is missing.
    DEEPANALYZE_MODEL: str = Field(default="deepanalyze-8b", env="DEEPANALYZE_MODEL")
    # A reasonable default fallback model installed locally via Ollama (phi3:mini is available offline)
    DEEPANALYZE_FALLBACK_MODEL: str = Field(default="phi3:mini", env="DEEPANALYZE_FALLBACK_MODEL")
    DEEPANALYZE_TIMEOUT: int = Field(default=20, env="DEEPANALYZE_TIMEOUT")
    # Allow falling back to local models when the preferred model isn't available. Safe for dev.
    DEEPANALYZE_ALLOW_FALLBACK: bool = Field(default=True, env="DEEPANALYZE_ALLOW_FALLBACK")

    # Security / Limits
<<<<<<< HEAD
    MAX_UPLOAD_SIZE_MB: int = Field(default=50, env="MAX_UPLOAD_SIZE_MB")
    
=======
    MAX_UPLOAD_SIZE_MB: int = Field(default=50)
    LLM_PROVIDER: str = Field(default="auto")
    REPORT_NARRATOR_TIMEOUT_SECONDS: int = Field(default=20)
    AUTO_TRAIN_TARGET_CONFIDENCE: float = Field(default=0.65)
    MIN_ROWS_FOR_PREDICTION: int = Field(default=30)

>>>>>>> 15b8a6d8 (new1)
    # Authentication
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production", env="SECRET_KEY")
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # Database
    # Expect a full async SQLAlchemy-compatible DATABASE_URL, e.g.
    # postgresql+asyncpg://user:password@host:5432/dbname
    DATABASE_URL: str | None = Field(default=None, env="DATABASE_URL")
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    
    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND")
    
    # File Storage
    STORAGE_TYPE: str = Field(default="local", env="STORAGE_TYPE")  # local, minio, s3
    
    # MinIO Configuration
    MINIO_ENDPOINT: str = Field(default="localhost:9000", env="MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin", env="MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = Field(default="minioadmin", env="MINIO_SECRET_KEY")
    MINIO_BUCKET: str = Field(default="dataverse", env="MINIO_BUCKET")
    MINIO_SECURE: bool = Field(default=False, env="MINIO_SECURE")
    
    # AWS S3 Configuration
    AWS_REGION: str = Field(default="us-east-1", env="AWS_REGION")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    AWS_S3_BUCKET: str = Field(default="dataverse", env="AWS_S3_BUCKET")
    
    # Claude AI
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    CLAUDE_MODEL: str = Field(default="claude-sonnet-4-6", env="CLAUDE_MODEL")

    # Sentry
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.1, env="SENTRY_TRACES_SAMPLE_RATE")
    SENTRY_PROFILES_SAMPLE_RATE: float = Field(default=0.0, env="SENTRY_PROFILES_SAMPLE_RATE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def trusted_hosts_list(self) -> List[str]:
        return [host.strip() for host in self.TRUSTED_HOSTS.split(",") if host.strip()]


settings = Settings()
