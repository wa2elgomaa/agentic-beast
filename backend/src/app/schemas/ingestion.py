"""Ingestion API request and response schemas."""

from datetime import date, datetime
from typing import Dict, List, Optional, Any
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


# ============================================================================
# Task Management Schemas
# ============================================================================


class IngestionTaskCreate(BaseModel):
    """Request to create an ingestion task."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    adaptor_type: str = Field(..., description="'gmail', 'webhook', or 'manual'")
    adaptor_config: Optional[Dict] = None
    schedule_type: str = Field(default="none", description="'none', 'once', or 'recurring'")
    cron_expression: Optional[str] = None
    run_at: Optional[datetime] = None

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "name": "Daily Gmail Sync",
                "adaptor_type": "gmail",
                "adaptor_config": {"gmail_query": "has:attachment is:unread", "sheet_name": "Sheet1"},
                "schedule_type": "recurring",
                "cron_expression": "0 9 * * *",
            }
        }


class IngestionTaskUpdate(BaseModel):
    """Request to update an ingestion task."""

    name: Optional[str] = None
    description: Optional[str] = None
    adaptor_config: Optional[Dict] = None
    schedule_type: Optional[str] = None
    cron_expression: Optional[str] = None
    run_at: Optional[datetime] = None
    status: Optional[str] = None


class IngestionTaskResponse(BaseModel):
    """Response with ingestion task details."""

    id: UUID
    name: str
    description: Optional[str]
    adaptor_type: str
    adaptor_config: Optional[Dict]
    schedule_type: str
    cron_expression: Optional[str]
    run_at: Optional[datetime]
    status: str
    deduplication_enabled: bool
    dedup_lookback_imports: Optional[int]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True


class IngestionTaskRunResponse(BaseModel):
    """Response with task run details."""

    id: UUID
    task_id: UUID
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    rows_inserted: int
    rows_updated: int
    rows_failed: int
    total_rows_processed: int
    total_duplicates_found: int
    total_deltas_calculated: int
    deduplication_enabled: bool
    error_message: Optional[str]
    error_type: Optional[str]  # data_error, auth_error, network_error
    error_code: Optional[str]  # invalid_grant, unauthorized, etc.
    run_metadata: Optional[Dict]
    created_at: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True


class DeduplicationSummaryResponse(BaseModel):
    """Summary of deduplication results for a run."""

    run_id: UUID
    total_rows_processed: int
    total_duplicates_found: int
    total_deltas_calculated: int
    deduplication_enabled: bool
    duplicates_summary: Dict[str, Any]  # Detailed breakdown of duplicates


# ============================================================================
# Schema Mapping Schemas
# ============================================================================


class SchemaDetectResponse(BaseModel):
    """Response with detected columns and auto-mapping."""

    source_columns: List[str] = Field(..., description="Detected source columns")
    auto_mapped: Dict[str, str] = Field(..., description="{source: target} auto-mapped fields")
    unmatched: List[str] = Field(..., description="Columns that couldn't be auto-mapped")


class SchemaMappingUpdate(BaseModel):
    """Request to save/update task schema mapping."""

    source_columns: List[str]
    field_mappings: Dict[str, Any]  # {source: target or {target, is_metric, is_datetime_split, datetime_split_companion_field}}
    identifier_column: Optional[str] = None  # Column name for cross-platform deduplication
    dedup_config: Optional[Dict[str, Any]] = None  # Deduplication strategy configuration
    template_id: Optional[UUID] = None  # Optional: apply existing template


class SchemaMappingTemplateCreate(BaseModel):
    """Request to create a schema mapping template."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    source_columns: List[str]
    field_mappings: Dict[str, str]


class SchemaMappingTemplateResponse(BaseModel):
    """Response with schema mapping template details."""

    id: UUID
    name: str
    description: Optional[str]
    source_columns: List[str]
    field_mappings: Dict[str, str]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True


class TaskSchemaMappingResponse(BaseModel):
    """Response with task schema mapping details."""

    id: UUID
    task_id: UUID
    template_id: Optional[UUID]
    source_columns: List[str]
    field_mappings: Dict[str, Any]  # Can include per-field config with is_metric, is_datetime_split, etc.
    identifier_column: Optional[str]  # Column name for cross-platform matching
    dedup_config: Optional[Dict[str, Any]]  # Deduplication strategy configuration
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True


class SaveAsTemplateRequest(BaseModel):
    """Request to save a task mapping as a reusable template."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


# ============================================================================
# Webhook Schemas
# ============================================================================


class WebhookPayload(BaseModel):
    """Generic webhook payload."""

    # Allow any fields for flexibility
    class Config:
        """Pydantic config."""
        extra = "allow"


class WebhookTestRequest(BaseModel):
    """Request to test webhook delivery."""

    payload: Dict = Field(..., description="Webhook payload to test")


# ============================================================================
# Gmail OAuth Schemas
# ============================================================================


class GmailAuthUrlRequest(BaseModel):
    """Request to generate Gmail OAuth URL for a task."""

    redirect_uri: str = Field(..., description="Frontend/backend callback URI configured in Google OAuth app")


class GmailAuthUrlResponse(BaseModel):
    """Response containing Gmail OAuth URL."""

    auth_url: str
    state: str


class GmailExchangeCodeRequest(BaseModel):
    """Request to exchange OAuth code for Gmail user tokens."""

    code: str
    state: str
    redirect_uri: str


class GmailExchangeCodeResponse(BaseModel):
    """Response after successful Gmail OAuth code exchange."""

    task_id: UUID
    connected_email: str
    message: str = "Gmail account linked successfully"



# ============================================================================
# Gmail Credential Management Schemas
# ============================================================================


class CredentialStatusResponse(BaseModel):
    """Current credential status and health information."""

    task_id: UUID
    status: str  # active | expired | invalid | needs_refresh | pending_auth
    health_score: int  # 0-100
    account_email: Optional[str]
    consecutive_failures: int
    max_consecutive_failures: int
    last_used_at: Optional[str]
    auth_established_at: Optional[str]
    token_refreshed_at: Optional[str]
    last_error_code: Optional[str]
    last_error_message: Optional[str]
    created_at: str
    updated_at: str


class CredentialAuditLogEntryResponse(BaseModel):
    """Individual credential audit log entry."""

    id: UUID
    task_id: UUID
    event_type: str  # authenticated | token_refreshed | auth_failed | invalidated | manually_cleared
    account_email: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    action_by: Optional[UUID]
    created_at: str


class CredentialAuditLogResponse(BaseModel):
    """Paginated credential audit log."""

    audit_log: List[CredentialAuditLogEntryResponse]
    limit: int
    offset: int
    total: int
