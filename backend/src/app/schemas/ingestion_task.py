"""SQLAlchemy models for ingestion tasks, runs, schema mappings, and file uploads."""

from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

from sqlalchemy import Boolean, Enum as SQLEnum, Float, Integer, String, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .document import Base


class AdaptorType(str, Enum):
    """Supported adaptor types."""
    GMAIL = "gmail"
    WEBHOOK = "webhook"
    MANUAL = "manual"


class ScheduleType(str, Enum):
    """Schedule types for recurring tasks."""
    ONCE = "once"
    RECURRING = "recurring"
    NONE = "none"


class TaskStatus(str, Enum):
    """Status of ingestion task."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class RunStatus(str, Enum):
    """Status of a task run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELED = "canceled"


class DeduplicationStrategy(str, Enum):
    """Metric handling strategies for duplicate rows."""
    SUBTRACT = "subtract"  # New value - sum(previous values) = delta
    KEEP = "keep"  # Use new value only (replace old)
    ADD = "add"  # Sum all values (cumulative: new + sum(previous))
    SUM = "sum"  # Same as ADD, keep last value
    SKIP = "skip"  # Don't store duplicate (already have this metric)

    @staticmethod
    def get_description(strategy: str) -> str:
        """Get human-readable description of strategy."""
        descriptions = {
            "subtract": "Calculate delta (new - previous sum) - use for weekly/daily metrics",
            "keep": "Keep new value only (replace) - use for current state metrics",
            "add": "Sum all values (cumulative) - use for lifetime totals",
            "sum": "Cumulative sum - same as Add",
            "skip": "Skip duplicate - don't store if already processed",
        }
        return descriptions.get(strategy, "Unknown strategy")


class IngestionTask(Base):
    """Ingestion task configuration."""
    
    __tablename__ = "ingestion_tasks"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Task metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Adaptor configuration
    adaptor_type: Mapped[str] = mapped_column(SQLEnum(AdaptorType, native_enum=False), nullable=False)
    adaptor_config: Mapped[Optional[dict]] = mapped_column(JSONB)  # Adaptor-specific config (e.g. gmail_query, webhook_secret)
    
    # Scheduling
    schedule_type: Mapped[str] = mapped_column(SQLEnum(ScheduleType, native_enum=False), nullable=False, default=ScheduleType.NONE)
    cron_expression: Mapped[Optional[str]] = mapped_column(String(255))  # e.g. "0 9 * * *" for 9 AM daily
    run_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)  # For once-only tasks
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(SQLEnum(TaskStatus, native_enum=False), nullable=False, default=TaskStatus.ACTIVE)

    # Test execution configuration
    test_execution_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    test_execution_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    # Deduplication configuration
    deduplication_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dedup_lookback_imports: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Number of previous imports to check for duplicates

    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    runs: Mapped[list["IngestionTaskRun"]] = relationship("IngestionTaskRun", back_populates="task", cascade="all, delete-orphan")
    schema_mapping: Mapped[Optional["TaskSchemaMapping"]] = relationship("TaskSchemaMapping", back_populates="task", uselist=False, cascade="all, delete-orphan")
    uploaded_files: Mapped[list["UploadedFile"]] = relationship("UploadedFile", back_populates="task", cascade="all, delete-orphan")
    test_runs: Mapped[list["CronTestRun"]] = relationship("CronTestRun", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """String representation."""
        return f"<IngestionTask(id={self.id}, name='{self.name}', adaptor_type='{self.adaptor_type}')>"


class IngestionTaskRun(Base):
    """A single execution/run of an ingestion task."""
    
    __tablename__ = "ingestion_task_runs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False)
    parent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_task_runs.id", ondelete="CASCADE"), nullable=True)

    # Execution metadata
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    
    # Run status
    status: Mapped[str] = mapped_column(SQLEnum(RunStatus, native_enum=False), nullable=False, default=RunStatus.PENDING)
    
    # Results
    rows_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_type: Mapped[Optional[str]] = mapped_column(String(50))  # data_error, auth_error, network_error
    error_code: Mapped[Optional[str]] = mapped_column(String(50))  # invalid_grant, unauthorized, etc.

    # Deduplication tracking
    total_rows_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_duplicates_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_deltas_calculated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deduplication_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Failed email tracking
    failed_emails_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_emails_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Celery task tracking for graceful cancellation
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Metadata
    run_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)  # e.g. {"file_name": "...", "email_subject": "..."}
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    
    # Relationships
    task: Mapped["IngestionTask"] = relationship("IngestionTask", back_populates="runs")
    uploaded_files: Mapped[list["UploadedFile"]] = relationship("UploadedFile", back_populates="run", cascade="all, delete-orphan")
    parent_run: Mapped[Optional["IngestionTaskRun"]] = relationship("IngestionTaskRun", remote_side=[id], back_populates="child_runs", foreign_keys=[parent_run_id])
    child_runs: Mapped[list["IngestionTaskRun"]] = relationship("IngestionTaskRun", back_populates="parent_run", remote_side=[parent_run_id], cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """String representation."""
        return f"<IngestionTaskRun(id={self.id}, task_id={self.task_id}, status='{self.status}')>"


class SchemaMappingTemplate(Base):
    """Reusable schema mapping template."""
    
    __tablename__ = "schema_mapping_templates"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Template metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Schema configuration
    source_columns: Mapped[list] = mapped_column(JSONB, nullable=False)  # ["col1", "col2", ...]
    field_mappings: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"source_col": "target_field", ...}
    
    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    task_mappings: Mapped[list["TaskSchemaMapping"]] = relationship("TaskSchemaMapping", back_populates="template")

    def __repr__(self) -> str:
        """String representation."""
        return f"<SchemaMappingTemplate(id={self.id}, name='{self.name}')>"


class TaskSchemaMapping(Base):
    """Per-task schema mapping (can optionally reference a template)."""
    
    __tablename__ = "task_schema_mappings"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False, unique=True)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("schema_mapping_templates.id", ondelete="SET NULL"), nullable=True)
    
    # Schema configuration
    source_columns: Mapped[list] = mapped_column(JSONB, nullable=False)  # ["col1", "col2", ...]
    field_mappings: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"source_col": "target_field", ...}

    # Field configuration metadata (stored in field_mappings for backward compatibility)
    # field_mappings can include per-field config:
    # {
    #   "source_col": {
    #     "target": "target_field",
    #     "is_metric": true,  # Mark as metric column for delta calculation
    #     "is_datetime_split": true,  # Split date/time into separate fields
    #     "datetime_split_companion_field": "published_time"  # Companion field name
    #   }
    # }

    # Identifier configuration
    identifier_column: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Column name for exact-match deduplication
    connection_strategy_identifier_column: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Column name for cross-platform content linking

    # Deduplication strategy configuration
    # Stored as JSONB to support per-field strategies:
    # {
    #   "default_strategy": "subtract",  # Global default strategy
    #   "field_strategies": {
    #     "video_views": "subtract",  # Weekly views - calculate delta
    #     "total_followers": "keep",   # Current follower count - keep latest
    #     "lifetime_reach": "add",     # Lifetime metric - sum all
    #   }
    # }
    dedup_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Dedup strategy configuration

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    task: Mapped["IngestionTask"] = relationship("IngestionTask", back_populates="schema_mapping")
    template: Mapped[Optional["SchemaMappingTemplate"]] = relationship("SchemaMappingTemplate", back_populates="task_mappings")

    def __repr__(self) -> str:
        """String representation."""
        return f"<TaskSchemaMapping(id={self.id}, task_id={self.task_id}, template_id={self.template_id})>"


class UploadedFile(Base):
    """Uploaded file tracking."""
    
    __tablename__ = "uploaded_files"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys (both nullable for flexibility)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=True)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_task_runs.id", ondelete="CASCADE"), nullable=True)
    
    # File metadata
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # in bytes
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # pending|processing|processed|failed
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    
    # Relationships
    task: Mapped[Optional["IngestionTask"]] = relationship("IngestionTask", back_populates="uploaded_files")
    run: Mapped[Optional["IngestionTaskRun"]] = relationship("IngestionTaskRun", back_populates="uploaded_files")

    def __repr__(self) -> str:
        """String representation."""
        return f"<UploadedFile(id={self.id}, filename='{self.original_filename}', s3_key='{self.s3_key}')>"


class CronTestRun(Base):
    """Test execution record for monitoring cron task scheduling."""

    __tablename__ = "cron_test_runs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign key
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False)

    # Execution details
    executed_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # SUCCESS, FAILED, TIMEOUT
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    task: Mapped["IngestionTask"] = relationship("IngestionTask", back_populates="test_runs")

    def __repr__(self) -> str:
        """String representation."""
        return f"<CronTestRun(id={self.id}, task_id={self.task_id}, status='{self.status}')>"


class GmailCredentialStatus(Base):
    """Track the status and health of Gmail OAuth credentials."""

    __tablename__ = "gmail_credential_status"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending_auth")
    health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    account_email: Mapped[Optional[str]] = mapped_column(String(255))
    scopes: Mapped[Optional[str]] = mapped_column(Text)
    
    last_used_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    last_auth_attempt_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    auth_established_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    token_refreshed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    
    last_error_code: Mapped[Optional[str]] = mapped_column(String(50))
    last_error_message: Mapped[Optional[str]] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    task: Mapped["IngestionTask"] = relationship("IngestionTask", foreign_keys=[task_id])

    def __repr__(self) -> str:
        """String representation."""
        return f"<GmailCredentialStatus(task_id={self.task_id}, status=\'{self.status}\', health={self.health_score})>"


class GmailCredentialAuditLog(Base):
    """Audit trail for Gmail credential lifecycle events."""

    __tablename__ = "gmail_credential_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False)
    
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    account_email: Mapped[Optional[str]] = mapped_column(String(255))
    error_code: Mapped[Optional[str]] = mapped_column(String(50))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(JSONB)
    action_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    
    task: Mapped["IngestionTask"] = relationship("IngestionTask", foreign_keys=[task_id])

    def __repr__(self) -> str:
        """String representation."""
        return f"<GmailCredentialAuditLog(task_id={self.task_id}, event_type=\'{self.event_type}\')>"



class IngestionDeduplication(Base):
    """Track deduplication actions and delta calculations for row matching."""

    __tablename__ = "ingestion_deduplication"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key to the run this deduplication tracking is for
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_task_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Row tracking
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    cleaned_identifier: Mapped[str] = mapped_column(String(150), nullable=False)
    beast_uuid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Deduplication status and action
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_connection_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # True if matched via connection_strategy_identifier, False if exact match
