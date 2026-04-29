"""Pydantic schemas for tags API (Phase 2).

Schemas for CRUD operations, bulk upload, and re-embedding task.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class TagCreateRequest(BaseModel):
    """Request to create a new tag."""

    slug: str = Field(
        description="Unique tag identifier (lowercase, hyphenated)",
        min_length=1,
        max_length=100,
        pattern="^[a-z0-9-]+$",
    )
    name: str = Field(
        description="Human-readable tag name",
        min_length=1,
        max_length=255,
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional tag description",
        max_length=1000,
    )
    variations: Optional[List[str]] = Field(
        default=None,
        description="List of keyword variations/synonyms for matching",
        max_items=20,
    )
    is_primary: bool = Field(
        default=False,
        description="If true, this is a primary/top-level category tag",
    )


class TagUpdateRequest(BaseModel):
    """Request to update an existing tag."""

    name: Optional[str] = Field(
        default=None,
        description="Update tag name",
        max_length=255,
    )
    description: Optional[str] = Field(
        default=None,
        description="Update tag description",
        max_length=1000,
    )
    variations: Optional[List[str]] = Field(
        default=None,
        description="Update keyword variations",
        max_items=20,
    )
    is_primary: Optional[bool] = Field(
        default=None,
        description="Update primary status",
    )
    re_embed: bool = Field(
        default=False,
        description="If true, trigger re-embedding of this tag (updates vector)",
    )


class TagResponse(BaseModel):
    """Response schema for a single tag."""

    slug: str
    name: str
    description: Optional[str] = None
    variations: Optional[List[str]] = None
    is_primary: bool
    embedding_dim: Optional[int] = Field(
        default=None,
        description="Dimension of embedding (384 if computed, None if missing)",
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TagListResponse(BaseModel):
    """Response for listing tags."""

    items: List[TagResponse] = Field(description="List of tags")
    total: int = Field(description="Total tag count")
    limit: int = Field(description="Limit used in query")
    offset: int = Field(description="Offset used in query")


class TagBulkUploadRequest(BaseModel):
    """Request for bulk tag upload (CSV format via multipart)."""

    # Note: In API router, this will be received as a multipart form with:
    # - file (UploadFile): CSV file with columns: slug, name, description, variations, is_primary
    # The following fields are for structured upload (optional alternative)

    tags: Optional[List[TagCreateRequest]] = Field(
        default=None,
        description="List of tags to create (alternative to CSV file)",
        max_items=1000,
    )
    auto_embed: bool = Field(
        default=True,
        description="If true, automatically generate embeddings after upload",
    )
    skip_duplicates: bool = Field(
        default=True,
        description="If true, skip tags with existing slugs; if false, raise error",
    )


class TagBulkUploadResponse(BaseModel):
    """Response from bulk tag upload."""

    created_count: int = Field(description="Number of tags created")
    skipped_count: int = Field(description="Number of duplicate slugs skipped")
    failed_count: int = Field(description="Number of tags that failed to create")
    errors: List[str] = Field(description="Error messages from failed uploads")
    embedding_task_id: Optional[str] = Field(
        default=None,
        description="Celery task ID for async re-embedding (if auto_embed=true)",
    )


class TagReEmbedRequest(BaseModel):
    """Request to re-embed tags (generate/update vectors)."""

    tag_slugs: Optional[List[str]] = Field(
        default=None,
        description="If provided, re-embed only these tags; if None, re-embed all",
        max_items=10000,
    )
    batch_size: int = Field(
        default=100,
        description="Number of tags to process per Celery task batch",
        ge=1,
        le=1000,
    )


class TagReEmbedResponse(BaseModel):
    """Response from re-embed request."""

    task_id: str = Field(description="Celery task ID for tracking re-embedding progress")
    tags_to_embed: int = Field(description="Number of tags scheduled for embedding")
    batch_count: int = Field(description="Number of Celery tasks created")
    message: str = Field(
        default="Re-embedding task submitted; check status with GET /admin/tags/embed-status/{task_id}"
    )


class TagReEmbedStatusResponse(BaseModel):
    """Status of a tag re-embedding task."""

    task_id: str
    status: str = Field(description="Task status: pending/progress/completed/failed")
    embedded_count: int = Field(description="Tags successfully embedded")
    failed_count: int = Field(description="Tags that failed to embed")
    total_count: int = Field(description="Total tags in task")
    progress_percent: int = Field(description="Estimated progress (0-100)")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class TagFeedbackRequest(BaseModel):
    """Request to record tag feedback (suggestions kept vs. removed by editor)."""

    article_id: str = Field(
        description="ID of the article being tagged",
        min_length=1,
        max_length=255,
    )
    suggested_tags: List[str] = Field(
        description="List of tags suggested by ML model (tag slugs)",
        default_factory=list,
    )
    kept_tags: List[str] = Field(
        description="List of tags kept by editor (tag slugs)",
        default_factory=list,
    )


class TagFeedbackResponse(BaseModel):
    """Response from tag feedback endpoint."""

    article_id: str
    feedback_records: int = Field(description="Number of feedback records created")
    message: str = Field(default="Tag feedback recorded successfully")
