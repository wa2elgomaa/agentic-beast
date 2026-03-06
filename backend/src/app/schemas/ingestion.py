"""Ingestion API request and response schemas."""

from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExcelRow(BaseModel):
    """Single row from Excel report."""

    sheet_name: str
    row_number: int
    report_date: date
    platform: str
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    reach: Optional[int] = None
    impressions: Optional[int] = None
    engagement_rate: Optional[float] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    saves: Optional[int] = None


class RowError(BaseModel):
    """Error in processing a row."""

    row_number: int
    error: str


class IngestTriggerRequest(BaseModel):
    """Request to trigger ingestion."""

    source: str = Field(default="gmail", description="Ingestion source (gmail, manual, etc.)")
    file_name: Optional[str] = Field(None, description="Optional file name for manual ingestion")


class IngestResult(BaseModel):
    """Result of an ingestion operation."""

    rows_inserted: int
    rows_updated: int
    rows_failed: int
    errors: List[RowError]


class IngestTriggerResponse(BaseModel):
    """Response to ingestion trigger."""

    task_id: UUID = Field(..., description="Celery task ID")
    status: str = Field(default="queued", description="Task status")
    message: str = Field(default="Ingestion task queued for processing")


class IngestStatusResponse(BaseModel):
    """Status of ingestion task."""

    task_id: UUID
    status: str  # queued, processing, completed, failed
    result: Optional[IngestResult] = None
    error: Optional[str] = None
    progress: Optional[dict] = None  # {processed, total, percentage}
