"""Article scraper API endpoints (Phase 2, T095).

Endpoints for triggering and monitoring article scraping from CMS.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
import structlog

from app.auth import verify_admin
from app.tasks.article_scraper import scrape_articles_task

logger = structlog.get_logger(__name__)

router = APIRouter()


class ScrapeStartResponse(BaseModel):
    """Response when starting a scrape task."""

    task_id: str = Field(description="Celery task ID for tracking")
    message: str = Field(default="Article scraping started")
    batch_size: int = Field(description="Articles per CMS API request")


class ScrapeStatusResponse(BaseModel):
    """Status of a scraping task."""

    task_id: str
    status: str = Field(description="Task status: pending/progress/completed/failed")
    total_ingested: int = Field(default=0, description="Articles successfully ingested")
    total_skipped: int = Field(default=0, description="Articles skipped (already exist)")
    total_failed: int = Field(default=0, description="Articles that failed to ingest")
    error: str | None = Field(default=None, description="Error message if failed")


@router.post("/admin/articles/scrape", response_model=ScrapeStartResponse, tags=["admin-articles"])
async def start_article_scrape(
    batch_size: int = Query(default=50, ge=10, le=500),
    admin=Depends(verify_admin),
) -> ScrapeStartResponse:
    """Start an article scraping task from CMS.

    **Required**: Admin role

    Fetches articles from CMS in batches and ingests them into `article_vectors`
    table with pgvector embeddings. Runs as async Celery task.

    Args:
        batch_size: Number of articles per CMS API request (default 50).

    Returns:
        Task ID for monitoring progress with GET /admin/articles/scrape-status/{task_id}
    """
    try:
        task = scrape_articles_task.delay(batch_size=batch_size)

        logger.info("Article scrape task started", task_id=task.id, batch_size=batch_size)

        return ScrapeStartResponse(
            task_id=task.id,
            batch_size=batch_size,
        )

    except Exception as exc:
        logger.error("Failed to start scrape task", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start scrape task",
        ) from exc


@router.get("/admin/articles/scrape-status/{task_id}", response_model=ScrapeStatusResponse, tags=["admin-articles"])
async def get_scrape_status(
    task_id: str,
    admin=Depends(verify_admin),
) -> ScrapeStatusResponse:
    """Get the status of an article scraping task.

    **Required**: Admin role

    Args:
        task_id: Celery task ID from start_article_scrape response.

    Returns:
        Task status with ingestion counts and any error messages.
    """
    from app.tasks.celery_app import celery_app

    try:
        task = celery_app.AsyncResult(task_id)

        if task.state == "PENDING":
            return ScrapeStatusResponse(
                task_id=task_id,
                status="pending",
            )
        elif task.state == "PROGRESS":
            info = task.info or {}
            return ScrapeStatusResponse(
                task_id=task_id,
                status="in_progress",
                total_ingested=info.get("total_ingested", 0),
                total_skipped=info.get("total_skipped", 0),
                total_failed=info.get("total_failed", 0),
            )
        elif task.state == "SUCCESS":
            result = task.result or {}
            return ScrapeStatusResponse(
                task_id=task_id,
                status="completed",
                total_ingested=result.get("total_ingested", 0),
                total_skipped=result.get("total_skipped", 0),
                total_failed=result.get("total_failed", 0),
            )
        elif task.state == "FAILURE":
            return ScrapeStatusResponse(
                task_id=task_id,
                status="failed",
                error=str(task.info),
            )
        else:
            return ScrapeStatusResponse(
                task_id=task_id,
                status=task.state.lower(),
            )

    except Exception as exc:
        logger.error("Failed to get scrape status", task_id=task_id, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scrape status",
        ) from exc
