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
    ai_provider: Literal["openai", "bedrock", "ollama", "strands", "litert_lm"] = Field(default="openai")
    openai_api_key: str = Field(default="")
    openai_base_url: str = Field(default="")
    docker_model_runner_enabled: bool = Field(default=False)
    docker_model_runner_base_url: str = Field(default="http://model-runner.docker.internal/engines/v1")
    openai_model: str = Field(default="gpt-4")
    openai_sql_model: str = Field(default="")
    openai_intent_model: str = Field(default="")
    openai_parse_model: str = Field(default="")
    openai_tag_model: str = Field(default="")
    openai_recommendation_model: str = Field(default="")
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    openai_transcription_model: str = Field(default="gpt-4o-mini-transcribe")
    openai_vision_max_frames: int = Field(default=3)
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

    # LiteRT_LM Intent Classification Configuration
    litert_lm_enabled: bool = Field(default=True)
    litert_lm_intent_model: str = Field(default="litert-community/gemma-4-E2B-it-litert-lm")
    litert_lm_fallback_to_llm: bool = Field(default=True)
    litert_lm_min_confidence_threshold: float = Field(default=0.5)

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

    # ========== Agent Timeouts & Limits ==========
    
    # Agent LLM Timeouts (seconds)
    agent_analytics_timeout_seconds: int = Field(default=45)
    agent_tagging_timeout_seconds: int = Field(default=30)
    agent_recommendation_timeout_seconds: int = Field(default=90)
    agent_intent_classifier_timeout_seconds: int = Field(default=15)
    agent_router_timeout_seconds: int = Field(default=20)
    
    # SQL Generation
    sql_generation_max_retries: int = Field(default=2)
    sql_generation_retry_multiplier: float = Field(default=1.5)
    
    # Tagging Configuration
    tagging_max_tags: int = Field(default=10)
    tagging_min_tags: int = Field(default=3)
    
    # Recommendation Configuration
    recommendation_max_results: int = Field(default=20)
    
    # ========== Code Interpreter Settings ==========
    
    code_interpreter_timeout_seconds: int = Field(default=30)
    code_interpreter_max_lines: int = Field(default=30)
    code_interpreter_max_length_chars: int = Field(default=5000)
    code_interpreter_restricted_python_enabled: bool = Field(default=True)
    
    # ========== Database Settings ==========
    
    db_statement_timeout_ms: int = Field(default=10000)
    db_max_rows_per_query: int = Field(default=200)
    db_default_limit: int = Field(default=20)
    db_query_cache_ttl_seconds: int = Field(default=300)
    analytics_top_n_max: int = Field(default=20)
    publishing_insights_default_days: int = Field(default=90)
    publishing_insights_min_days: int = Field(default=7)
    publishing_insights_max_days: int = Field(default=365)
    
    # ========== Value Guard Settings ==========
    
    value_guard_enabled: bool = Field(default=True)
    value_guard_threshold: int = Field(default=100)
    
    # ========== Retry Policy ==========
    
    retry_max_attempts: int = Field(default=3)
    retry_base_delay_seconds: float = Field(default=1.0)
    retry_max_delay_seconds: float = Field(default=60.0)
    retry_backoff_multiplier: float = Field(default=2.0)
    retry_jitter_enabled: bool = Field(default=True)
    
    # ========== Text Sanitization ==========
    
    text_sanitize_max_length_default: int = Field(default=800)
    text_sanitize_max_length_errors: int = Field(default=600)
    text_sanitize_max_length_descriptions: int = Field(default=1200)
    text_sanitize_remove_non_printable: bool = Field(default=True)
    
    # ========== API Timeouts ==========
    
    http_client_timeout_seconds: float = Field(default=60.0)
    external_api_timeout_seconds: float = Field(default=30.0)
    
    # ========== Follow-up Detection ==========
    
    followup_detection_enabled: bool = Field(default=True)
    followup_use_conversation_context: bool = Field(default=True)
    followup_confidence_threshold: float = Field(default=0.6)
    
    # ========== Few-Shot Configuration ==========
    
    few_shot_dynamic_generation_enabled: bool = Field(default=True)
    few_shot_num_examples_per_intent: int = Field(default=3)
    few_shot_cache_locally: bool = Field(default=True)
    few_shot_fallback_to_stored: bool = Field(default=True)
    
    # ========== Configuration Directories ==========
    
    config_dir: str = Field(default="config")

    # ========== Multimodal / Realtime Chat ==========

    multimodal_enabled: bool = Field(default=False)
    multimodal_provider: Literal["polar"] = Field(default="polar")
    multimodal_model_path: str = Field(default="")
    multimodal_tts_backend: Literal["auto", "mlx", "onnx"] = Field(default="auto")
    multimodal_max_sessions: int = Field(default=2)
    multimodal_max_audio_bytes: int = Field(default=2_000_000)
    multimodal_max_image_bytes: int = Field(default=5_000_000)
    multimodal_default_language: str = Field(default="en-US")

    @computed_field
    @property
    def effective_openai_base_url(self) -> str:
        """Resolve OpenAI-compatible base URL, preferring Docker Model Runner when enabled."""
        if self.docker_model_runner_enabled:
            return (self.docker_model_runner_base_url or "").strip().rstrip("/")

        configured = (self.openai_base_url or "").strip()
        return configured or "https://api.openai.com/v1"

    @computed_field
    @property
    def effective_openai_api_key(self) -> str:
        """Resolve API key for OpenAI-compatible clients.

        Docker Model Runner does not require an OpenAI key, but the SDK client
        still expects a non-empty value.
        """
        if self.docker_model_runner_enabled:
            return "docker-model-runner"
        return self.openai_api_key

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
