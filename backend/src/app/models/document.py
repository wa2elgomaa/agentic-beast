"""SQLAlchemy models for the documents table."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, Integer, Numeric, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Document(Base):
    """Documents table model - analytics records and document chunks."""
    
    __tablename__ = "documents"

    # Primary key and metadata
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sheet_name: Mapped[str] = mapped_column(Text, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    doc_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(384))

    # Profile & Post Information  
    published_date: Mapped[Optional[date]] = mapped_column(Date)
    reported_at: Mapped[Optional[date]] = mapped_column(Date)
    profile_name: Mapped[Optional[str]] = mapped_column(Text)
    profile_url: Mapped[Optional[str]] = mapped_column(Text)
    profile_id: Mapped[Optional[str]] = mapped_column(Text)
    post_detail_url: Mapped[Optional[str]] = mapped_column(Text)
    content_id: Mapped[Optional[str]] = mapped_column(Text)

    # Platform & Content Classification
    platform: Mapped[Optional[str]] = mapped_column(Text)
    content_type: Mapped[Optional[str]] = mapped_column(Text)
    media_type: Mapped[Optional[str]] = mapped_column(Text)
    origin_of_the_content: Mapped[Optional[str]] = mapped_column(Text)

    # Content Details
    title: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    author_url: Mapped[Optional[str]] = mapped_column(Text)
    author_id: Mapped[Optional[str]] = mapped_column(Text)
    author_name: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    link_url: Mapped[Optional[str]] = mapped_column(Text)
    view_on_platform: Mapped[Optional[str]] = mapped_column(Text)

    # Engagement Metrics
    organic_interactions: Mapped[Optional[int]] = mapped_column(Integer)
    total_interactions: Mapped[Optional[int]] = mapped_column(Integer)
    total_reactions: Mapped[Optional[int]] = mapped_column(Integer)
    total_comments: Mapped[Optional[int]] = mapped_column(Integer)
    total_shares: Mapped[Optional[int]] = mapped_column(Integer)
    unpublished: Mapped[Optional[bool]] = mapped_column(Boolean)
    engagements: Mapped[Optional[int]] = mapped_column(Integer)

    # Reach Metrics
    total_reach: Mapped[Optional[int]] = mapped_column(Integer)
    paid_reach: Mapped[Optional[int]] = mapped_column(Integer)
    organic_reach: Mapped[Optional[int]] = mapped_column(Integer)

    # Impression Metrics
    total_impressions: Mapped[Optional[int]] = mapped_column(Integer)
    paid_impressions: Mapped[Optional[int]] = mapped_column(Integer)
    organic_impressions: Mapped[Optional[int]] = mapped_column(Integer)
    reach_engagement_rate: Mapped[Optional[float]] = mapped_column(Numeric)

    # Video Metrics
    total_likes: Mapped[Optional[int]] = mapped_column(Integer)
    video_length_sec: Mapped[Optional[int]] = mapped_column(Integer)
    video_views: Mapped[Optional[int]] = mapped_column(Integer)
    total_video_view_time_sec: Mapped[Optional[int]] = mapped_column(Integer)
    avg_video_view_time_sec: Mapped[Optional[float]] = mapped_column(Numeric)
    completion_rate: Mapped[Optional[float]] = mapped_column(Numeric)

    # Labels & Categorization
    labels: Mapped[Optional[str]] = mapped_column(Text)
    label_groups: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __repr__(self) -> str:
        """String representation."""
        return f"<Document(id={self.id}, sheet_name='{self.sheet_name}', row_number={self.row_number})>"