"""Celery task for article scraping (Phase 2, T094).

Periodically fetches articles from CMS and populates article_vectors table.
"""

from __future__ import annotations

import structlog

from app.logging import get_logger
from app.tasks.celery_app import celery_app, run_async_in_worker

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.article_scraper.scrape_articles_task",
    max_retries=2,
    default_retry_delay=300,  # 5 minute retry
)
def scrape_articles_task(
    self,
    batch_size: int = 50,
) -> dict:
    """Scrape articles from CMS and ingest to article_vectors (Phase 2).

    Args:
        batch_size: Number of articles to fetch per CMS API request.

    Returns:
        Dict with total_ingested, total_skipped, total_failed counts.
    """
    async def run_scrape():
        from app.services.article_scraper_service import ArticleScraperService

        logger.info("Starting article scraper task", batch_size=batch_size)

        try:
            scraper = ArticleScraperService()
            result = await scraper.scrape_all_articles(batch_size=batch_size)

            logger.info("Article scraper completed", **result)
            return result

        except Exception as exc:
            logger.error("Article scraper failed: %s", exc, exc_info=True)
            raise

    try:
        return run_async_in_worker(run_scrape())
    except Exception as exc:
        logger.error("Scrape articles task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc) from exc
