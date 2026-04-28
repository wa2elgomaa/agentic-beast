"""Pydantic schemas for document upload and status API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Response returned when a document is submitted for processing."""

    task_id: str = Field(description="Celery task ID for tracking processing status")
    filename: str = Field(description="Original filename of the uploaded document")
    file_size_bytes: int = Field(description="Size of the uploaded file in bytes")
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
