"""Application configuration using Pydantic V2 Settings."""

import logging
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server Configuration
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_debug: bool = Field(default=False)
    api_title: str = Field(default="Agentic Beast API")
    api_version: str = Field(default="0.1.0")
    environment: Literal["development", "staging", "production"] = Field(default="development")

    # Database Configuration
    database_url: str = Field(default="postgresql+asyncpg://beast:beast@localhost:5432/beast")
    database_echo: bool = Field(default=False)
    database_pool_size: int = Field(default=20)
    database_max_overflow: int = Field(default=10)
    database_pool_timeout: int = Field(default=30)
    database_pool_recycle: int = Field(default=3600)

    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Celery Configuration
    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")
    celery_task_track_started: bool = Field(default=True)
    celery_task_time_limit: int = Field(default=3600)

    # JWT Authentication
    jwt_secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_hours: int = Field(default=24)

    # Auth Provider Configuration
    auth_provider: Literal["local", "ldap"] = Field(default="local")
    ldap_server: str = Field(default="ldap://localhost:389")
    ldap_base_dn: str = Field(default="dc=example,dc=com")
    ldap_bind_dn: str = Field(default="cn=admin,dc=example,dc=com")
    ldap_bind_password: str = Field(default="")

    # Password Reset
    password_reset_token_ttl_minutes: int = Field(default=60)
    frontend_url: str = Field(default="http://localhost:3000")

    # SMTP Configuration
    smtp_server: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_email: str = Field(default="noreply@example.com")
    smtp_from_name: str = Field(default="Agentic Beast")
    smtp_use_tls: bool = Field(default=True)

    # Gmail Configuration
    gmail_credentials_path: str = Field(default="./credentials.json")
    gmail_oauth_client_id: str = Field(default="")
    gmail_oauth_client_secret: str = Field(default="")
    gmail_oauth_token_uri: str = Field(default="https://oauth2.googleapis.com/token")
    gmail_inbox_query: str = Field(default="")
    gmail_email_monitor_interval_seconds: int = Field(default=300)

    # CMS API Configuration
    cms_api_base_url: str = Field(default="http://localhost:3000/api")
    cms_api_timeout: int = Field(default=10)

    # MongoDB Configuration
    mongodb_uri: str = Field(default="mongodb://localhost:27017/articles_db")

    # AI Provider Configuration
    ai_provider: Literal["openai", "bedrock", "ollama", "strands"] = Field(default="openai")
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4")
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    openai_agent_id: str = Field(default="")  # OpenAI Agent ID (e.g. asst_xxxxx)
    openai_workflow_id: str = Field(default="")

    # Ollama Local LLM Configuration
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="mistral")
    # Model used specifically for SQL generation — deepseek-coder:6.7b recommended
    ollama_sql_model: str = Field(default="")
    # Model used specifically for intent classification — qwen2.5-coder recommended
    ollama_intent_model: str = Field(default="")
    ollama_embedding_model: str = Field(default="nomic-embed-text")

    # Agent Session Encryption (OpenAI Agents SDK EncryptedSession)
    agent_session_encryption_key: str = Field(default="")
    agent_session_ttl_seconds: int = Field(default=86400)

    # AWS Bedrock Configuration
    aws_region: str = Field(default="us-east-1")
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    bedrock_model_id: str = Field(default="anthropic.claude-3-sonnet-20240229-v1:0")

    # Embedding Service Configuration
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_batch_size: int = Field(default=32)
    embedding_device: Literal["cpu", "cuda"] = Field(default="cpu")

    # Document Processing Configuration
    document_chunk_size: int = Field(default=1000)
    document_chunk_overlap: int = Field(default=200)
    document_max_file_size_mb: int = Field(default=50)

    # Observability Configuration
    structlog_level: str = Field(default="INFO")
    prometheus_enabled: bool = Field(default=True)
    prometheus_port: int = Field(default=9090)
    sentry_dsn: str = Field(default="")
    sentry_environment: str = Field(default="development")
    sentry_sample_rate: float = Field(default=0.1)

    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_calls: int = Field(default=100)
    rate_limit_period: int = Field(default=60)

    # Watched Folder Configuration
    watched_folder_path: str = Field(default="./watched_documents/")

    # Logging Configuration
    log_level: str = Field(default="INFO")
    timezone: str = Field(default="UTC")
    
    # Monitoring & Observability
    prometheus_enabled: bool = Field(default=True, env="PROMETHEUS_ENABLED")

    # AWS S3 Configuration (for file uploads)
    s3_bucket: str = Field(default="agentic-beast-ingestion")
    s3_prefix: str = Field(default="uploads")
    s3_endpoint_url: str = Field(default="")  # Optional: for localstack or S3-compatible services

    # APScheduler Configuration
    apscheduler_enabled: bool = Field(default=True)
    apscheduler_timezone: str = Field(default="UTC")

    @computed_field
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @computed_field
    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"

    def get_logger(self) -> logging.Logger:
        """Get a configured logger."""
        return logging.getLogger(__name__)


# Global settings instance
settings = Settings()
