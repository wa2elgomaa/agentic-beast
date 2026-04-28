"""Document upload API router.

Provides:
- POST /documents/upload — upload a document for chunked ingestion
- GET /documents/status/{task_id} — check processing status
"""

from __future__ import annotations

import os
import tempfile
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.users import get_current_user
from app.config import settings
from app.db.session import get_db_session
from app.logging import get_logger
from app.schemas.documents import DocumentStatus, DocumentUploadResponse
from app.schemas.user import User

logger = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Supported MIME types
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/octet-stream",  # generic fallback
}

_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".xlsx", ".xls", ".csv"}

_MAX_FILE_SIZE = getattr(settings, "document_max_file_size_mb", 50) * 1024 * 1024  # bytes


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a company document for RAG ingestion",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF, Excel, or text document to ingest")],
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentUploadResponse:
    """Upload a company document and queue it for processing.

    The file is temporarily saved to disk and a Celery task is dispatched
    to chunk, embed, and store the content in the documents table.

    Supports: PDF, Excel (.xlsx/.xls), CSV, plain text (.txt/.md)
    """
    filename = file.filename or "upload"

    # Validate file extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    # Read file content (enforce max size)
    contents = await file.read()
    if len(contents) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {settings.document_max_file_size_mb} MB.",
        )

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Save to a temp file that the Celery worker can read
    suffix = ext
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, prefix="beast_doc_"
        ) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
    except OSError as exc:
        logger.error("Failed to save upload to temp file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file.",
        )

    logger.info(
        "Document upload received",
        filename=filename,
        size_bytes=len(contents),
        tmp_path=tmp_path,
    )

    # Dispatch Celery task
    from app.tasks.document_ingest import ingest_document  # local import

    task = ingest_document.delay(file_path=tmp_path, filename=filename)

    return DocumentUploadResponse(
        task_id=task.id,
        filename=filename,
        file_size_bytes=len(contents),
        message="Document queued for processing",
    )


@router.get(
    "/status/{task_id}",
    response_model=DocumentStatus,
    summary="Check document processing status",
)
async def get_document_status(
    task_id: str,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> DocumentStatus:
    """Check the processing status of a previously uploaded document."""
    from app.tasks.celery_app import celery_app  # local import

    try:
        result = celery_app.AsyncResult(task_id)
        state = result.state

        if state == "PENDING":
            return DocumentStatus(task_id=task_id, status="pending")

        if state == "STARTED":
            return DocumentStatus(task_id=task_id, status="processing")

        if state == "SUCCESS":
            info = result.result or {}
            return DocumentStatus(
                task_id=task_id,
                filename=info.get("filename", ""),
                status="completed",
                chunks_created=info.get("chunks_created"),
            )

        if state == "FAILURE":
            return DocumentStatus(
                task_id=task_id,
                status="failed",
                error=str(result.result) if result.result else "Unknown error",
            )

        return DocumentStatus(task_id=task_id, status=state.lower())

    except Exception as exc:
        logger.error("Failed to retrieve task status for %s: %s", task_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve task status.",
        )
