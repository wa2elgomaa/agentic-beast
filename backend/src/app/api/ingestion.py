"""Ingestion API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.logging import get_logger
from app.schemas.ingestion import IngestStatusResponse, IngestTriggerRequest, IngestTriggerResponse
from app.services.ingestion_service import get_ingestion_service
from app.tasks.celery_app import celery_app
from app.tasks.excel_ingest import process_excel_file

logger = get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/trigger", response_model=IngestTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion(
    request: IngestTriggerRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Trigger data ingestion from configured sources.

    Args:
        request: Ingestion trigger request.
        db: Database session.

    Returns:
        Task ID and status.
    """
    logger.info("Ingestion triggered", source=request.source)

    try:
        if request.source == "gmail":
            # Queue Gmail monitoring task
            task = celery_app.send_task("app.tasks.email_monitor.monitor_gmail_inbox")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown ingestion source: {request.source}",
            )

        return IngestTriggerResponse(
            task_id=UUID(task.id),
            status="queued",
            message=f"Ingestion task queued for {request.source}",
        )

    except Exception as e:
        logger.error("Failed to queue ingestion task", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue ingestion task",
        )


@router.get("/status/{task_id}", response_model=IngestStatusResponse)
async def get_ingestion_status(task_id: UUID):
    """Get status of an ingestion task.

    Args:
        task_id: Celery task ID.

    Returns:
        Task status and result.
    """
    try:
        task = celery_app.AsyncResult(str(task_id))

        if task.state == "PENDING":
            return IngestStatusResponse(
                task_id=task_id,
                status="queued",
            )
        elif task.state == "PROGRESS":
            return IngestStatusResponse(
                task_id=task_id,
                status="processing",
                progress=task.info,
            )
        elif task.state == "SUCCESS":
            return IngestStatusResponse(
                task_id=task_id,
                status="completed",
                result=task.result,
            )
        elif task.state == "FAILURE":
            return IngestStatusResponse(
                task_id=task_id,
                status="failed",
                error=str(task.info),
            )
        else:
            return IngestStatusResponse(
                task_id=task_id,
                status=task.state.lower(),
            )

    except Exception as e:
        logger.error("Failed to get task status", task_id=str(task_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get task status",
        )


@router.post("/manual", response_model=IngestTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_excel(file: UploadFile = File(...)):
    """Upload and process Excel file manually.

    Args:
        file: Excel file to process.

    Returns:
        Task ID and status.
    """
    try:
        if not file.filename.lower().endswith(".xlsx"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an Excel (.xlsx) file",
            )

        # Read file
        file_data = await file.read()

        # Queue Excel ingestion task
        task = process_excel_file.delay(file_data, file.filename)

        logger.info("Manual Excel ingestion queued", filename=file.filename)

        return IngestTriggerResponse(
            task_id=UUID(task.id),
            status="queued",
            message=f"Excel file '{file.filename}' queued for processing",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to queue manual ingestion", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process file",
        )
