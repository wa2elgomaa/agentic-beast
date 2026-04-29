"""SQLAlchemy models for Phase 2 entities."""

from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON, UUID, ForeignKey, Index, Integer, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.db.base import Base


class ArticleVectorModel(Base):
    """Model for vectorized CMS articles (pgvector corpus)."""
    
    __tablename__ = "article_vectors"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id = Column(String(255), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=False)  # 384-dimensional vector as list
    published_at = Column(DateTime(timezone=True), nullable=True)
    article_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("idx_article_vectors_article_id", "article_id"),
        Index("idx_article_vectors_deleted_at", "deleted_at"),
        Index("idx_article_vectors_created_at", "created_at"),
    )


class AppSettingModel(Base):
    """Model for runtime application settings."""
    
    __tablename__ = "app_settings"
    
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    is_secret = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index("idx_app_settings_is_secret", "is_secret"),
        Index("idx_app_settings_updated_at", "updated_at"),
    )


class WebhookEventModel(Base):
    """Model for webhook event audit trail and deduplication."""
    
    __tablename__ = "webhook_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(255), nullable=True)  # Unique event ID from CMS for deduplication
    source = Column(String(50), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False)
    hmac_verified = Column(Boolean, default=False, nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index("idx_webhook_events_event_id", "event_id"),
        Index("idx_webhook_events_source_type", "source", "event_type"),
        Index("idx_webhook_events_processed_at", "processed_at"),
        Index("idx_webhook_events_created_at", "created_at"),
    )


class TagFeedbackModel(Base):
    """Model for tag suggestion feedback (SC-003 acceptance rate measurement)."""
    
    __tablename__ = "tag_feedback"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id = Column(String(255), nullable=False)
    tag_slug = Column(String(255), nullable=False)
    was_kept = Column(Boolean, nullable=False)  # True = user kept suggestion, False = user removed
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index("idx_tag_feedback_article_id", "article_id"),
        Index("idx_tag_feedback_tag_slug", "tag_slug"),
        Index("idx_tag_feedback_recorded_at", "recorded_at"),
    )


class DatasetModel(Base):
    """A collection of documents grouped for RAG / embedding purposes."""

    __tablename__ = "datasets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    allowed_extensions = Column(JSON, nullable=False, default=list)  # e.g. [".pdf", ".docx"]
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    files = relationship("DatasetFileModel", back_populates="dataset", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_datasets_slug", "slug"),
        Index("idx_datasets_created_at", "created_at"),
    )


class DatasetFileModel(Base):
    """A single file belonging to a dataset."""

    __tablename__ = "dataset_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    s3_key = Column(String(1000), nullable=False)
    file_size_bytes = Column(Integer, nullable=False, default=0)
    content_type = Column(String(200), nullable=True)
    # Embedding / ingestion status: pending | processing | embedded | failed
    embed_status = Column(String(50), nullable=False, default="pending")
    embed_task_id = Column(String(255), nullable=True)
    chunks_created = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    dataset = relationship("DatasetModel", back_populates="files")

    __table_args__ = (
        Index("idx_dataset_files_dataset_id", "dataset_id"),
        Index("idx_dataset_files_embed_status", "embed_status"),
        Index("idx_dataset_files_uploaded_at", "uploaded_at"),
    )
