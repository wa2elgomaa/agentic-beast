"""Celery tasks for webhook ingestion and article vectorization."""

from typing import Dict, List, Any, Optional
import asyncio
import structlog
from celery import shared_task
from sqlalchemy import select, insert, update, func
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.db.session import AsyncSessionLocal
from app.models import ArticleVectorModel, WebhookEventModel
from app.services.embedding_service import get_embedding_service
from app.tools.cms_tools import fetch_article_by_id

logger = structlog.get_logger(__name__)


@shared_task(bind=True, max_retries=3)
def process_article_webhook_task(self, article_id: str, event_type: str = "article.published") -> Dict[str, Any]:
    """Process article webhook event: fetch, chunk, embed, and upsert to article_vectors.
    
    Args:
        article_id: Article ID from CMS.
        event_type: Type of event (published, updated, deleted).
        
    Returns:
        Dict with processing result.
    """
    try:
        # Handle soft-delete for article.deleted events
        if event_type == "article.deleted":
            return asyncio.run(_handle_article_deletion(article_id))
        
        # For published/updated events: fetch, chunk, embed
        return asyncio.run(_process_article_update(article_id))

    except Exception as exc:
        logger.error("Article webhook task failed", article_id=article_id, error=str(exc))
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@shared_task(bind=True, max_retries=2)
def process_generic_webhook_task(
    self,
    source: str,
    event_type: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None
) -> Dict[str, Any]:
    """Process generic webhook event: log to webhook_events table.
    
    Args:
        source: Event source (e.g., 'cms').
        event_type: Type of event.
        payload: Event payload.
        event_id: Unique event ID for deduplication.
        
    Returns:
        Dict with processing result.
    """
    try:
        return asyncio.run(_log_webhook_event(source, event_type, payload, event_id))

    except Exception as exc:
        logger.error("Generic webhook task failed", source=source, event_type=event_type, error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


async def _handle_article_deletion(article_id: str) -> Dict[str, Any]:
    """Handle article.deleted webhook: soft-delete in article_vectors."""
    from datetime import datetime, timezone
    
    async with AsyncSessionLocal() as session:
        stmt = update(ArticleVectorModel).where(
            ArticleVectorModel.article_id == article_id
        ).values({
            ArticleVectorModel.deleted_at: datetime.now(timezone.utc)
        })
        
        result = await session.execute(stmt)
        await session.commit()
        
        logger.info("Article soft-deleted", article_id=article_id, rows_updated=result.rowcount)
        
        return {
            "article_id": article_id,
            "event_type": "article.deleted",
            "status": "completed",
            "rows_deleted": result.rowcount
        }


async def _process_article_update(article_id: str) -> Dict[str, Any]:
    """Fetch article, chunk, embed, and upsert to article_vectors."""
    try:
        # Fetch article from CMS
        article_content = await fetch_article_by_id(article_id)
        if not article_content:
            logger.warning("Article not found in CMS", article_id=article_id)
            return {
                "article_id": article_id,
                "status": "failed",
                "message": "Article not found in CMS"
            }

        # Chunk content
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=512,
            chunk_overlap=64,
        )
        chunks = splitter.split_text(article_content.get("content", ""))
        
        if not chunks:
            logger.warning("No chunks generated", article_id=article_id)
            return {
                "article_id": article_id,
                "status": "failed",
                "message": "No chunks generated"
            }

        # Embed chunks (use first chunk as representative embedding for article)
        embedding_service = get_embedding_service()
        embedding = await embedding_service.embed_text(chunks[0])
        
        if not embedding:
            logger.error("Embedding generation failed", article_id=article_id)
            return {
                "article_id": article_id,
                "status": "failed",
                "message": "Embedding generation failed"
            }

        # Upsert to article_vectors
        async with AsyncSessionLocal() as session:
            # Check if exists
            stmt = select(ArticleVectorModel).where(
                ArticleVectorModel.article_id == article_id
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.content = "\n".join(chunks)
                existing.embedding = embedding
                existing.updated_at = asyncio.get_event_loop().time()
                await session.commit()
                action = "updated"
            else:
                new_row = ArticleVectorModel(
                    article_id=article_id,
                    content="\n".join(chunks),
                    embedding=embedding,
                    metadata=article_content.get("metadata", {})
                )
                session.add(new_row)
                await session.commit()
                action = "created"

            logger.info("Article vectorized", article_id=article_id, action=action, chunks=len(chunks))

        return {
            "article_id": article_id,
            "status": "completed",
            "action": action,
            "chunks": len(chunks)
        }

    except Exception as e:
        logger.error("Article processing failed", article_id=article_id, error=str(e))
        raise


async def _log_webhook_event(
    source: str,
    event_type: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None
) -> Dict[str, Any]:
    """Log webhook event to webhook_events table."""
    async with AsyncSessionLocal() as session:
        event = WebhookEventModel(
            event_id=event_id,
            source=source,
            event_type=event_type,
            payload=payload,
            hmac_verified=False,  # Will be set by webhooks endpoint
            processed_at=func.now()
        )
        session.add(event)
        await session.commit()

        logger.info("Webhook event logged", event_id=event_id, source=source, event_type=event_type)

        return {
            "event_id": event_id,
            "source": source,
            "event_type": event_type,
            "status": "completed"
        }
