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
    
    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    runs: Mapped[list["IngestionTaskRun"]] = relationship("IngestionTaskRun", back_populates="task", cascade="all, delete-orphan")
    schema_mapping: Mapped[Optional["TaskSchemaMapping"]] = relationship("TaskSchemaMapping", back_populates="task", uselist=False, cascade="all, delete-orphan")
    uploaded_files: Mapped[list["UploadedFile"]] = relationship("UploadedFile", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """String representation."""
        return f"<IngestionTask(id={self.id}, name='{self.name}', adaptor_type='{self.adaptor_type}')>"


class IngestionTaskRun(Base):
    """A single execution/run of an ingestion task."""
    
    __tablename__ = "ingestion_task_runs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False)
    
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
    
    # Metadata
    run_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)  # e.g. {"file_name": "...", "email_subject": "..."}
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    
    # Relationships
    task: Mapped["IngestionTask"] = relationship("IngestionTask", back_populates="runs")
    uploaded_files: Mapped[list["UploadedFile"]] = relationship("UploadedFile", back_populates="run", cascade="all, delete-orphan")

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
