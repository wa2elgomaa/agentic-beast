"""Celery task for re-embedding tags with pgvector (Phase 2, T091).

Generates or updates embeddings for tags in async batches.
Handles progress tracking and error reporting.
"""

from __future__ import annotations

from typing import Optional
import structlog

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.tasks.celery_app import celery_app, run_async_in_worker
from sqlalchemy import select, func

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.tag_embedding.re_embed_tags_task",
    max_retries=2,
    default_retry_delay=60,
)
def re_embed_tags_task(
    self,
    tag_slugs: Optional[list[str]] = None,
    batch_size: int = 100,
) -> dict:
    """Re-embed tags with updated vectors for pgvector search (Phase 2).

    Fetches tags, generates/updates embeddings, and persists to database.

    Args:
        tag_slugs: List of specific tag slugs to embed; if None, embeds all tags.
        batch_size: Number of tags to process per worker (not used directly here,
                   but available for potential batch scheduling).

    Returns:
        Dict with embedded, failed, and total counts.
    """
    async def run_embedding():
        from app.schemas.tag import Tag as TagModel
        from app.services.embedding_service import EmbeddingService

        logger.info("Starting tag re-embedding", tag_slugs=tag_slugs)

        embedding_svc = EmbeddingService()
        embedded_count = 0
        failed_count = 0

        async with AsyncSessionLocal() as session:
            # Fetch tags to embed
            if tag_slugs:
                stmt = select(TagModel).where(TagModel.slug.in_(tag_slugs))
            else:
                stmt = select(TagModel)

            result = await session.execute(stmt)
            tags = result.scalars().all()
            total_count = len(tags)

            logger.info("Embedding tags", total=total_count)

            # Embed each tag
            for idx, tag in enumerate(tags, start=1):
                try:
                    # Generate embedding from tag name + description
                    text_to_embed = f"{tag.name} {tag.description or ''}".strip()[:2000]

                    if not text_to_embed:
                        logger.warning("Tag has no content to embed", slug=tag.slug)
                        failed_count += 1
                        continue

                    embedding = embedding_svc.embed_text(text_to_embed)

                    if not embedding:
                        logger.warning("Embedding service returned None", slug=tag.slug)
                        failed_count += 1
                        continue

                    # Update tag with embedding
                    tag.embedding = embedding
                    embedded_count += 1

                    # Report progress every 10 tags
                    if idx % 10 == 0:
                        logger.info("Embedding progress", embedded=embedded_count, total=total_count)
                        self.update_state(
                            state="PROGRESS",
                            meta={"embedded": embedded_count, "failed": failed_count, "total": total_count},
                        )

                except Exception as exc:
                    logger.error("Failed to embed tag", slug=tag.slug, error=str(exc))
                    failed_count += 1

            # Commit all changes
            try:
                await session.commit()
                logger.info(
                    "Tag embedding completed",
                    embedded=embedded_count,
                    failed=failed_count,
                    total=total_count,
                )
            except Exception as exc:
                logger.error("Failed to save embeddings", error=str(exc))
                await session.rollback()
                return {
                    "embedded": 0,
                    "failed": total_count,
                    "total": total_count,
                    "error": f"Database commit failed: {str(exc)}",
                }

        return {
            "embedded": embedded_count,
            "failed": failed_count,
            "total": total_count,
        }

    try:
        return run_async_in_worker(run_embedding())
    except Exception as exc:
        logger.error("Tag re-embedding task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc) from exc
