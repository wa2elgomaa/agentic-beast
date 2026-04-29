"""Article scraper service for Phase 2 (T093).

Fetches articles from CMS and populates article_vectors table with:
- Article content
- Computed embeddings
- Metadata tracking
"""

from __future__ import annotations

from typing import Optional, List
import structlog

from app.config import settings
from app.services.embedding_service import EmbeddingService
from app.db.session import AsyncSessionLocal
from app.models.phase2 import ArticleVectorModel
from sqlalchemy import select, text as sql_text

logger = structlog.get_logger(__name__)


class ArticleScraperService:
    """Service for fetching and ingesting articles into pgvector."""

    def __init__(self):
        """Initialize scraper service."""
        self.cms_api_base_url = settings.cms_api_base_url.rstrip("/")
        self.cms_api_timeout = getattr(settings, "cms_api_timeout", 10)
        self.cms_api_key = getattr(settings, "cms_api_key", "")
        self.batch_size = getattr(settings, "cms_scrape_batch_size", 50)
        self.concurrency = getattr(settings, "cms_scrape_concurrency", 4)

    async def fetch_articles_from_cms(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Fetch articles from CMS REST API.

        Args:
            limit: Number of articles to fetch (max 1000 per request).
            offset: Pagination offset.

        Returns:
            List of article dicts with id, title, body, content, published_at, etc.
        """
        import httpx
        import json

        limit = min(limit, 1000)
        url = f"{self.cms_api_base_url}/articles?limit={limit}&offset={offset}"

        headers = {}
        if self.cms_api_key:
            headers["X-API-Key"] = self.cms_api_key

        try:
            async with httpx.AsyncClient(timeout=self.cms_api_timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                logger.info(
                    "Fetched articles from CMS",
                    limit=limit,
                    offset=offset,
                    count=len(data.get("articles", [])),
                )

                return data.get("articles", [])

        except Exception as exc:
            logger.error("Failed to fetch articles from CMS: %s", exc)
            return []

    async def ingest_articles_to_vectors(
        self,
        articles: List[dict],
        skip_existing: bool = True,
    ) -> dict:
        """Ingest articles into article_vectors table.

        Args:
            articles: List of article dicts from CMS.
            skip_existing: If true, skip articles already in article_vectors.

        Returns:
            Dict with ingested, skipped, failed counts.
        """
        embedding_svc = EmbeddingService()
        ingested_count = 0
        skipped_count = 0
        failed_count = 0

        async with AsyncSessionLocal() as session:
            for article in articles:
                try:
                    article_id = str(article.get("id") or article.get("cms_id") or "")
                    if not article_id:
                        logger.warning("Article missing ID", article=article)
                        failed_count += 1
                        continue

                    # Check if already exists
                    if skip_existing:
                        stmt = select(ArticleVectorModel).where(
                            ArticleVectorModel.article_id == article_id
                        )
                        result = await session.execute(stmt)
                        if result.scalar_one_or_none():
                            skipped_count += 1
                            continue

                    # Extract content
                    title = str(article.get("title") or "")
                    body = str(article.get("body") or article.get("content") or "")

                    # Combine and truncate for embedding
                    combined_text = f"{title} {body}"[:2000]

                    if not combined_text.strip():
                        logger.warning("Article has no content", article_id=article_id)
                        failed_count += 1
                        continue

                    # Generate embedding
                    embedding = embedding_svc.embed_text(combined_text)

                    if not embedding:
                        logger.warning("Embedding service returned None", article_id=article_id)
                        failed_count += 1
                        continue

                    # Create or update article vector
                    metadata = {
                        "source": "cms_scraper",
                        "source_type": "cms_article",
                        "title_length": len(title),
                        "body_length": len(body),
                    }

                    # Upsert into article_vectors
                    stmt = sql_text("""
                        INSERT INTO article_vectors (article_id, content, embedding, metadata, published_at)
                        VALUES (:article_id, :content, :embedding::vector, :metadata::jsonb, :published_at)
                        ON CONFLICT (article_id)
                        DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            published_at = EXCLUDED.published_at,
                            updated_at = now()
                    """)

                    await session.execute(
                        stmt,
                        {
                            "article_id": article_id,
                            "content": combined_text,
                            "embedding": "[" + ",".join(str(v) for v in embedding) + "]",
                            "metadata": metadata,
                            "published_at": article.get("published_at"),
                        },
                    )

                    ingested_count += 1

                except Exception as exc:
                    logger.error(
                        "Failed to ingest article",
                        article_id=article.get("id"),
                        error=str(exc),
                    )
                    failed_count += 1

            await session.commit()

        logger.info(
            "Article ingestion completed",
            ingested=ingested_count,
            skipped=skipped_count,
            failed=failed_count,
        )

        return {
            "ingested": ingested_count,
            "skipped": skipped_count,
            "failed": failed_count,
        }

    async def scrape_all_articles(
        self,
        batch_size: Optional[int] = None,
    ) -> dict:
        """Scrape all articles from CMS and ingest to vectors.

        Args:
            batch_size: Articles per request (default from config).

        Returns:
            Dict with total stats (ingested, skipped, failed).
        """
        batch_size = batch_size or self.batch_size
        total_ingested = 0
        total_skipped = 0
        total_failed = 0
        offset = 0

        logger.info("Starting full article scrape")

        while True:
            # Fetch batch
            articles = await self.fetch_articles_from_cms(limit=batch_size, offset=offset)

            if not articles:
                logger.info("No more articles to fetch")
                break

            # Ingest batch
            result = await self.ingest_articles_to_vectors(articles)
            total_ingested += result["ingested"]
            total_skipped += result["skipped"]
            total_failed += result["failed"]

            offset += batch_size

            logger.info(
                "Batch processed",
                offset=offset,
                batch_ingested=result["ingested"],
                total_ingested=total_ingested,
            )

        logger.info(
            "Full scrape completed",
            total_ingested=total_ingested,
            total_skipped=total_skipped,
            total_failed=total_failed,
        )

        return {
            "total_ingested": total_ingested,
            "total_skipped": total_skipped,
            "total_failed": total_failed,
        }
