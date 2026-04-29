"""S3 document upload pipeline router for Phase 2.

Endpoint for uploading company documents directly to S3 and triggering ingest tasks.
"""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
import structlog

from app.config import settings
from app.schemas.documents import DocumentUploadResponse
from app.services.document_upload_service import DocumentUploadService
from app.auth import verify_admin  # Requires admin role for document uploads

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/upload", response_model=DocumentUploadResponse, tags=["Documents"])
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF, DOCX, or TXT document")],
    admin=Depends(verify_admin),
) -> DocumentUploadResponse:
    """Upload a company document to S3 and trigger ingestion.

    This endpoint:
    1. Validates file type and size (<100MB)
    2. Uploads file to S3 (dates-based path: documents/2024-01-15/filename.pdf)
    3. Submits async ingest task via Celery
    4. Returns S3 location and task ID for tracking

    **Required**: Admin role (JWT with role='admin')

    **File Types**: PDF, DOCX, TXT, XLSX (via document_processor)

    **Response**: S3 key, presigned URL, and Celery task ID

    ---

    Example:
    ```bash
    curl -X POST http://localhost:8000/api/documents/upload \\
      -H "Authorization: Bearer <token>" \\
      -F "file=@company_handbook.pdf"

    # Response:
    {
      "filename": "company_handbook.pdf",
      "s3_key": "documents/2024-01-15/company_handbook.pdf",
      "s3_url": "https://bucket.s3.amazonaws.com/documents/2024-01-15/company_handbook.pdf?...",
      "task_id": "abc123def456"
    }
    ```
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file selected")

    # File type validation
    allowed_extensions = {".pdf", ".docx", ".txt", ".xlsx"}
    file_ext = None
    if file.filename:
        import os

        file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not supported. Allowed: {', '.join(allowed_extensions)}",
        )

    try:
        upload_service = DocumentUploadService(
            bucket=settings.aws_s3_bucket,
            region=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
        )

        # Read file bytes
        file_bytes = await file.read()

        # File size validation (100MB limit)
        max_size_mb = 100
        if len(file_bytes) > max_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
                detail=f"File exceeds {max_size_mb}MB limit",
            )

        # Upload to S3 and submit ingest task
        response = await upload_service.upload_and_ingest(
            file_bytes=file_bytes,
            filename=file.filename or "document.pdf",
            content_type=file.content_type or "application/octet-stream",
        )

        logger.info(
            "Document uploaded successfully",
            filename=response.filename,
            s3_key=response.s3_key,
            task_id=response.task_id,
        )

        return response

    except Exception as exc:
        logger.error("Document upload failed", filename=file.filename, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document upload failed; see logs for details",
        ) from exc


@router.get("/ingest-status/{task_id}", tags=["Documents"])
async def get_ingest_status(task_id: str, admin=Depends(verify_admin)) -> dict:
    """Get the status of a document ingest task.

    **Required**: Admin role

    **Response**: Task status (pending/progress/completed/failed), progress info, error message

    ---

    Example:
    ```bash
    curl http://localhost:8000/api/documents/ingest-status/abc123def456 \\
      -H "Authorization: Bearer <token>"

    # Response:
    {
      "task_id": "abc123def456",
      "status": "completed",
      "filename": "company_handbook.pdf",
      "chunks_created": 42,
      "progress": 100
    }
    ```
    """
    from app.tasks.celery_app import celery_app

    task = celery_app.AsyncResult(task_id)

    if task.state == "PENDING":
        return {"task_id": task_id, "status": "pending", "progress": 0}
    elif task.state == "PROGRESS":
        return {
            "task_id": task_id,
            "status": "in_progress",
            "progress": task.info.get("current", 0),
        }
    elif task.state == "SUCCESS":
        return {
            "task_id": task_id,
            "status": "completed",
            "result": task.result,
        }
    elif task.state == "FAILURE":
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(task.info),
        }
    else:
        return {"task_id": task_id, "status": task.state}
