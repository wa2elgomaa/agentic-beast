"""Pydantic schemas for document upload and status API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Response returned when a document is submitted for processing.
    
    Phase 2: Includes S3 location and presigned URL for uploaded documents.
    """

    task_id: str = Field(description="Celery task ID for tracking processing status")
    filename: str = Field(description="Original filename of the uploaded document")
    file_size_bytes: Optional[int] = Field(
        default=None, description="Size of the uploaded file in bytes"
    )
    s3_key: str = Field(description="S3 object key (path) where file was stored")
    s3_url: Optional[str] = Field(
        default=None, description="Presigned S3 URL for document access (30-day expiry)"
    )
    message: str = Field(
        default="Document queued for processing",
        description="Human-readable status message",
    )


class DocumentStatus(BaseModel):
    """Status of a document processing task."""

    task_id: str = Field(description="Celery task ID")
    filename: str = Field(default="", description="Original filename")
    status: str = Field(
        description="Task status: pending | processing | completed | failed"
    )
    chunks_created: Optional[int] = Field(
        default=None,
        description="Number of text chunks created (available when completed)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if processing failed",
    )
