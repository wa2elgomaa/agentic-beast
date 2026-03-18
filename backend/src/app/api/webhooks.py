"""Webhook ingestion endpoints (public, no auth required)."""

import hmac
import hashlib
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Header
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.logging import get_logger
from app.models import IngestionTask
from app.schemas.ingestion import WebhookPayload
from app.services.ingestion_task_service import get_ingestion_task_service
from app.tasks.celery_app import celery_app
from sqlalchemy import select

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
