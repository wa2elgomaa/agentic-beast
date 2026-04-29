"""Webhook ingestion endpoints (public, no auth required)."""

import hmac
import hashlib
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Header, Depends, Query
from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_db_session
from app.logging import get_logger
from app.schemas import IngestionTask
from app.schemas.ingestion import WebhookPayload
from app.services.ingestion_task_service import get_ingestion_task_service
from app.tasks.celery_app import celery_app
from app.auth import verify_admin

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/webhooks/{task_id}", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    task_id: UUID,
    payload: WebhookPayload,
    x_hub_signature_256: str | None = Header(None),
    db: AsyncSession = Depends(get_db_session),
):
    """Receive webhook payload for an ingestion task.

    Requires HMAC-SHA256 signature validation via X-Hub-Signature-256 header.
    Header format: sha256=<signature>
    """
    try:
        # Get task from DB to validate and retrieve secret
        stmt = select(IngestionTask).where(IngestionTask.id == task_id)
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.adaptor_type != "webhook":
            raise HTTPException(status_code=400, detail="Task is not a webhook adaptor")

        # Validate HMAC signature
        webhook_secret = task.adaptor_config.get("webhook_secret", "")
        if not webhook_secret:
            logger.warning("No webhook secret configured for task", task_id=task_id)
            raise HTTPException(status_code=400, detail="Webhook not properly configured")

        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="X-Hub-Signature-256 header required")

        # Verify signature
        payload_str = payload.model_dump_json()
        expected_signature = "sha256=" + hmac.new(
            webhook_secret.encode(), payload_str.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(x_hub_signature_256, expected_signature):
            logger.warning("Invalid webhook signature", task_id=task_id)
            raise HTTPException(status_code=403, detail="Invalid signature")

        logger.info("Webhook signature validated", task_id=task_id)

        # Create and queue a task run
        service = get_ingestion_task_service(db)
        run = await service.create_run(task_id, run_metadata={"webhook_payload": payload.dict()})
        await db.commit()

        # Queue Celery task to process webhook
        celery_app.send_task(
            "app.tasks.ingestion_tasks.process_webhook_payload",
            args=[str(task_id), str(run.id), payload.dict()],
        )

        logger.info("Webhook processed", task_id=task_id, run_id=run.id)
        return {"status": "accepted", "run_id": str(run.id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Webhook processing failed", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail="Webhook processing failed")


# ── T114 ────────────────────────────────────────────────────────────────────

class WebhookEventResponse(BaseModel):
    id: str
    event_id: Optional[str]
    source: str
    event_type: str
    hmac_verified: bool
    processed_at: Optional[datetime]
    created_at: datetime


class WebhookEventsListResponse(BaseModel):
    items: list[WebhookEventResponse]
    total: int
    limit: int
    offset: int


@router.get("/admin/webhooks/events", response_model=WebhookEventsListResponse, tags=["admin-webhooks"])
async def list_webhook_events(
    source: Optional[str] = Query(default=None, description="Filter by source (e.g. cms)"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type (e.g. article.published)"),
    date_from: Optional[datetime] = Query(default=None, description="Filter events from this datetime (ISO 8601)"),
    date_to: Optional[datetime] = Query(default=None, description="Filter events up to this datetime (ISO 8601)"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin=Depends(verify_admin),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookEventsListResponse:
    """List webhook events for ops visibility (T114).

    Paginated and filterable by source, event_type, and date range.
    Requires admin JWT role claim.
    """
    from sqlalchemy import text

    # Build filter conditions
    where_clauses = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if source:
        where_clauses.append("source = :source")
        params["source"] = source
    if event_type:
        where_clauses.append("event_type = :event_type")
        params["event_type"] = event_type
    if date_from:
        where_clauses.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("created_at <= :date_to")
        params["date_to"] = date_to

    where_sql = " AND ".join(where_clauses)

    # Count total
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM webhook_events WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    # Fetch rows
    rows_result = await db.execute(
        text(
            f"""SELECT id, event_id, source, event_type, hmac_verified, processed_at, created_at
                FROM webhook_events
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset"""
        ),
        params,
    )
    rows = rows_result.fetchall()

    items = [
        WebhookEventResponse(
            id=str(row.id),
            event_id=row.event_id,
            source=row.source,
            event_type=row.event_type,
            hmac_verified=row.hmac_verified,
            processed_at=row.processed_at,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return WebhookEventsListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
