"""Phase 2 CMS article webhook receiver (public endpoint)."""

from typing import Optional
from fastapi import APIRouter, Request, HTTPException, status
import json
import structlog
from datetime import datetime, timezone
from sqlalchemy import func, select

from app.schemas.webhook_ingestion import WebhookPayload, WebhookResult
from app.utils.webhook_security import verify_hmac_signature
from app.tasks.webhook_ingest import process_article_webhook_task, process_generic_webhook_task
from app.db.session import AsyncSessionLocal
from app.models import WebhookEventModel

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["webhooks"])


@router.post("/webhook", response_model=WebhookResult, status_code=202)
async def receive_cms_webhook(request: Request) -> WebhookResult:
    """Receive and process a signed webhook from CMS (Phase 2).
    
    Expects:
    - X-TNN-Signature header: HMAC-SHA256 signature of raw body
    - JSON body with: source, event_type, event_id (optional), data
    
    Returns 202 Accepted immediately and queues Celery task for async processing.
    """
    from app.config import settings

    # Get raw body for HMAC verification
    body = await request.body()
    signature_header = request.headers.get("X-TNN-Signature")

    # Verify HMAC signature
    if not verify_hmac_signature(body, signature_header, settings.webhook_secret):
        logger.warning("Webhook signature verification failed", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    # Parse payload
    try:
        payload_dict = json.loads(body)
        payload = WebhookPayload(**payload_dict)
    except Exception as e:
        logger.warning("Failed to parse webhook payload", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload"
        )

    # Check for duplicate event_id (at-least-once deduplication)
    if payload.event_id:
        async with AsyncSessionLocal() as session:
            stmt = select(func.count()).select_from(WebhookEventModel).where(
                WebhookEventModel.event_id == payload.event_id
            )
            result = await session.execute(stmt)
            existing_count = result.scalar()
            
            if existing_count > 0:
                logger.info("Webhook event already processed (dedup)", event_id=payload.event_id)
                return WebhookResult(
                    event_id=payload.event_id,
                    routed_to="dedup_handler",
                    status="skipped",
                    message="Event already processed"
                )

    # Log webhook event to database (before routing)
    async with AsyncSessionLocal() as session:
        event = WebhookEventModel(
            event_id=payload.event_id,
            source=payload.source,
            event_type=payload.event_type,
            payload=payload_dict,
            hmac_verified=True
        )
        session.add(event)
        await session.commit()
        logger.info("Webhook event logged", event_id=payload.event_id, event_type=payload.event_type)

    # Route to appropriate handler based on event_type
    routed_to = "generic_handler"
    
    if payload.event_type in ("article.published", "article.updated"):
        article_id = payload.data.get("article_id")
        if not article_id:
            logger.warning("Missing article_id in article webhook", event_type=payload.event_type)
            return WebhookResult(
                event_id=payload.event_id,
                routed_to="none",
                status="failed",
                message="Missing article_id"
            )
        
        # Queue article webhook task
        process_article_webhook_task.delay(article_id, payload.event_type)
        routed_to = "article_webhook_handler"
        logger.info("Article webhook queued", article_id=article_id, event_type=payload.event_type)

    elif payload.event_type == "article.deleted":
        article_id = payload.data.get("article_id")
        if not article_id:
            logger.warning("Missing article_id in deletion webhook")
            return WebhookResult(
                event_id=payload.event_id,
                routed_to="none",
                status="failed",
                message="Missing article_id"
            )
        
        # Queue article deletion task
        process_article_webhook_task.delay(article_id, "article.deleted")
        routed_to = "article_deletion_handler"
        logger.info("Article deletion webhook queued", article_id=article_id)

    else:
        # Generic webhook handler
        process_generic_webhook_task.delay(
            payload.source,
            payload.event_type,
            payload_dict,
            payload.event_id
        )
        logger.info("Generic webhook queued", event_type=payload.event_type)

    return WebhookResult(
        event_id=payload.event_id,
        routed_to=routed_to,
        status="queued",
        message="Webhook received and queued for processing"
    )


@router.get("/webhook/events", status_code=200)
async def list_webhook_events(
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> dict:
    """List webhook events with optional filtering (admin endpoint).
    
    Args:
        source: Filter by webhook source.
        event_type: Filter by event type.
        limit: Max results to return.
        offset: Pagination offset.
        
    Returns:
        Paginated list of webhook events.
    """
    async with AsyncSessionLocal() as session:
        # Build query
        stmt = select(WebhookEventModel)
        
        if source:
            stmt = stmt.where(WebhookEventModel.source == source)
        if event_type:
            stmt = stmt.where(WebhookEventModel.event_type == event_type)
        
        # Count total
        count_stmt = select(func.count()).select_from(WebhookEventModel)
        if source:
            count_stmt = count_stmt.where(WebhookEventModel.source == source)
        if event_type:
            count_stmt = count_stmt.where(WebhookEventModel.event_type == event_type)
        
        count_result = await session.execute(count_stmt)
        total_count = count_result.scalar()
        
        # Order and paginate
        stmt = stmt.order_by(WebhookEventModel.created_at.desc()).offset(offset).limit(limit)
        result = await session.execute(stmt)
        items = result.scalars().all()
        
        return {
            "total": total_count,
            "offset": offset,
            "limit": limit,
            "items": [
                {
                    "id": str(e.id),
                    "event_id": e.event_id,
                    "source": e.source,
                    "event_type": e.event_type,
                    "hmac_verified": e.hmac_verified,
                    "processed_at": e.processed_at.isoformat() if e.processed_at else None,
                    "created_at": e.created_at.isoformat(),
                }
                for e in items
            ]
        }
