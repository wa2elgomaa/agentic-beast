"""Application configuration using Pydantic V2 Settings."""

import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import Field, computed_field, field_validator
from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    import yaml
    HAS_PYYAML = True
except Exception:
    HAS_PYYAML = False


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"

# Setup logging
logger = logging.getLogger(__name__)


def load_secret_from_aws_secrets_manager(
    secret_name: str,
    region_name: str = "us-east-1",
    json_key: Optional[str] = None
) -> Optional[str]:
    """
    Load a secret from AWS Secrets Manager.

    Args:
        secret_name: Name of the secret in Secrets Manager (e.g., "beast/production/db/postgres")
        region_name: AWS region
        json_key: If the secret is JSON, specify which key to extract

    Returns:
        Secret value as string, or None if not found
    """
    if not HAS_BOTO3:
        logger.warning(f"boto3 not installed, cannot load secret: {secret_name}")
        return None

    try:
        client = boto3.client("secretsmanager", region_name=region_name)
        response = client.get_secret_value(SecretId=secret_name)

        # Handle both string and binary secrets
        secret = response.get("SecretString") or response.get("SecretBinary")

        if not secret:
            logger.warning(f"Secret is empty: {secret_name}")
            return None

        # If json_key is specified, parse JSON and extract key
        if json_key:
            try:
                secret_dict = json.loads(secret)
                return secret_dict.get(json_key)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse secret as JSON: {secret_name}")
                return None

        return secret
    except Exception as e:
        logger.error(f"Failed to load secret '{secret_name}': {str(e)}")
        return None


def load_database_url_from_secrets(
    environment: str,
    region_name: str = "us-east-1"
) -> Optional[str]:
    """
    Load database URL from AWS Secrets Manager.

    Args:
        environment: Deployment environment (dev, staging, production)
        region_name: AWS region

    Returns:
        PostgreSQL connection URL
    """
    secret_name = f"beast/{environment}/db/postgres"

    try:
        if not HAS_BOTO3:
            return None

        client = boto3.client("secretsmanager", region_name=region_name)
        response = client.get_secret_value(SecretId=secret_name)
        secret = response.get("SecretString")

        if not secret:
            return None

        secret_dict = json.loads(secret)
        username = secret_dict.get("username", "beast")
        password = secret_dict.get("password", "")
        hostname = secret_dict.get("hostname", "localhost")
        port = secret_dict.get("port", 5432)
        database = secret_dict.get("database", "beast")

        # Build PostgreSQL URL
        return f"postgresql+asyncpg://{username}:{password}@{hostname}:{port}/{database}"
    except Exception as e:
        logger.error(f"Failed to load database URL from secrets: {str(e)}")
        return None


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

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate and normalize environment name."""
        if isinstance(v, str):
            v = v.lower()
            if v not in ("development", "staging", "production"):
                logger.warning(f"Unknown environment: {v}, defaulting to development")
                return "development"
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def load_database_url(cls, v: str, info) -> str:
        """Load database URL from AWS Secrets Manager if in production."""
        environment = info.data.get("environment", "development")

        # Only try to load from Secrets Manager if:
        # 1. In production/staging
        # 2. boto3 is available
        # 3. Using default/empty database URL
        if environment in ("production", "staging") and HAS_BOTO3:
            aws_region = info.data.get("aws_region", "us-east-1")
            db_url = load_database_url_from_secrets(environment, aws_region)
            if db_url:
                logger.info(f"Loaded database URL from AWS Secrets Manager for {environment}")
                return db_url

        return v

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
    openai_base_url: str = Field(default="")
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
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @computed_field
    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"

    @computed_field
    @property
    def model_settings(self) -> Dict[str, object]:
        """Load `model_settings.yaml` from the configured `config_dir` under backend.

        Returns an empty dict if the file is missing or PyYAML is not installed.
        """
        file_path = BASE_DIR / self.config_dir / "model_settings.yaml"
        if not file_path.exists():
            return {}

        if not HAS_PYYAML:
            logger.warning("PyYAML not installed; cannot parse model_settings.yaml")
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                return data or {}
        except Exception as e:
            logger.error(f"Failed to load model_settings.yaml: {e}")
            return {}

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

    def get_secret(
        self,
        secret_name: str,
        json_key: Optional[str] = None,
        default: Optional[str] = None
    ) -> Optional[str]:
        """
        Load a secret from AWS Secrets Manager with fallback to default.

        Usage:
            openai_key = settings.get_secret("beast/production/providers/openai", "api_key")

        Args:
            secret_name: Full secret name path
            json_key: If secret is JSON, which key to extract
            default: Default value if secret cannot be loaded

        Returns:
            Secret value or default
        """
        if self.is_production and HAS_BOTO3:
            value = load_secret_from_aws_secrets_manager(
                secret_name,
                region_name=self.aws_region,
                json_key=json_key
            )
            if value:
                return value

        return default

    def get_logger(self) -> logging.Logger:
        """Get a configured logger."""
        return logging.getLogger(__name__)


# Global settings instance
settings = Settings()
