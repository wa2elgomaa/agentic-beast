"""CMS API client tools for fetching and searching articles.

Provides:
- fetch_article_by_id: single article via CMS REST API
- search_articles: bulk search via direct MongoDB
- find_similar_articles: vector similarity search in MongoDB
- format_article_recommendation: structure a recommendation result
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any, Optional

import httpx
from strands import tool

from app.config import settings

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from body text."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _normalize_article(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw CMS article dict to a consistent schema."""
    body = _strip_html(str(raw.get("body") or raw.get("content") or ""))
    title = str(raw.get("title") or "")
    return {
        "id": str(raw.get("id") or raw.get("cms_id") or raw.get("_id") or ""),
        "title": title,
        "body": body,
        "excerpt": str(raw.get("excerpt") or body[:200]),
        "author": str(raw.get("author") or ""),
        "published_at": str(raw.get("published_at") or ""),
        "metadata": dict(raw.get("metadata") or {}),
        # Combined text for embedding — truncated to 2000 chars
        "content_for_embedding": (title + " " + body)[:2000],
    }


def _get_mongo_collection():
    """Return the motor AsyncIOMotorCollection for articles."""
    from motor.motor_asyncio import AsyncIOMotorClient  # local import

    uri = settings.mongodb_uri
    # Extract database name from URI or use default
    db_name = uri.rstrip("/").split("/")[-1] if "/" in uri.split("//")[-1] else "cms"
    collection_name = getattr(settings, "mongodb_articles_collection", "articles")
    client = AsyncIOMotorClient(uri)
    return client[db_name][collection_name]


# ---------------------------------------------------------------------------
# Public Strands tools
# ---------------------------------------------------------------------------

@tool
async def fetch_article_by_id(article_id: str) -> str:
    """Fetch a single article from the CMS REST API by its ID.

    Args:
        article_id: The CMS article ID to retrieve.

    Returns:
        JSON string with article fields: id, title, body, excerpt, author,
        published_at, metadata, content_for_embedding. Returns an error JSON
        on failure.
    """
    import json

    base_url = settings.cms_api_base_url.rstrip("/")
    timeout = getattr(settings, "cms_api_timeout", 10)
    api_key = getattr(settings, "cms_api_key", "")

    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key

    url = f"{base_url}/articles/{article_id}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)

        if response.status_code == 404:
            return json.dumps({"error": f"Article {article_id} not found", "status": 404})
        if response.status_code == 403:
            return json.dumps({"error": "Unauthorized — check CMS_API_KEY", "status": 403})
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            return json.dumps({"error": f"Rate limited. Retry after {retry_after}s", "status": 429})

        response.raise_for_status()
        raw = response.json()
        article = _normalize_article(raw)
        return json.dumps(article)

    except httpx.TimeoutException:
        _logger.error("CMS API timeout fetching article %s", article_id)
        return json.dumps({"error": "CMS API request timed out", "status": 504})
    except Exception as exc:
        _logger.error("CMS API error fetching article %s: %s", article_id, exc)
        return json.dumps({"error": str(exc), "status": 500})


@tool
async def search_articles(query: str, limit: int = 10) -> str:
    """Search articles directly in MongoDB using text search.

    Args:
        query: Search query string to match against article titles and bodies.
        limit: Maximum number of results to return (default 10, max 50).

    Returns:
        JSON string with list of matching articles (id, title, excerpt, published_at).
    """
    import json

    limit = min(limit, 50)

    try:
        collection = _get_mongo_collection()
        cursor = collection.find(
            {"$text": {"$search": query}},
            {"score": {"$meta": "textScore"}, "cms_id": 1, "title": 1, "excerpt": 1, "published_at": 1},
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)

        results = []
        async for doc in cursor:
            results.append({
                "id": str(doc.get("cms_id") or doc.get("_id") or ""),
                "title": str(doc.get("title") or ""),
                "excerpt": str(doc.get("excerpt") or "")[:200],
                "published_at": str(doc.get("published_at") or ""),
            })

        return json.dumps({"articles": results, "count": len(results)})

    except Exception as exc:
        _logger.error("MongoDB search error: %s", exc)
        return json.dumps({"error": str(exc), "articles": [], "count": 0})


@tool
async def find_similar_articles(article_id: str, limit: int = 5) -> str:
    """Find articles similar to a given article using vector similarity in MongoDB.

    Fetches the target article from the CMS API, generates an embedding, then
    performs a vector similarity search against the MongoDB articles collection.

    Args:
        article_id: The CMS article ID to find similar articles for.
        limit: Maximum number of similar articles to return (default 5, max 20).

    Returns:
        JSON string with list of similar articles including relevance scores.
    """
    import json

    limit = min(limit, 20)

    # 1. Fetch the target article
    article_json = await fetch_article_by_id(article_id)
    article_data = json.loads(article_json)
    if "error" in article_data:
        return article_json  # propagate error

    content = article_data.get("content_for_embedding") or article_data.get("title", "")
    if not content.strip():
        return json.dumps({"error": "Article has no content for embedding", "articles": []})

    # 2. Generate embedding for the article content
    try:
        from app.services.embedding_service import EmbeddingService  # local import

        embedding_svc = EmbeddingService()
        embedding = embedding_svc.embed_text(content)
    except Exception as exc:
        _logger.error("Embedding generation failed: %s", exc)
        return json.dumps({"error": f"Embedding failed: {exc}", "articles": []})

    # 3. Vector similarity search in MongoDB
    try:
        collection = _get_mongo_collection()
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "article_embedding_index",
                    "path": "embedding",
                    "queryVector": embedding,
                    "numCandidates": limit * 10,
                    "limit": limit + 1,  # +1 to exclude the query article itself
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "cms_id": 1,
                    "title": 1,
                    "excerpt": 1,
                    "published_at": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        cursor = collection.aggregate(pipeline)

        results = []
        async for doc in cursor:
            doc_id = str(doc.get("cms_id") or "")
            if doc_id == article_id:
                continue  # skip the source article
            results.append(format_article_recommendation(
                article_id=doc_id,
                title=str(doc.get("title") or ""),
                excerpt=str(doc.get("excerpt") or "")[:200],
                published_at=str(doc.get("published_at") or ""),
                relevance_score=float(doc.get("score") or 0.0),
            ))
            if len(results) >= limit:
                break

        return json.dumps({"articles": results, "count": len(results), "source_article_id": article_id})

    except Exception as exc:
        _logger.error("MongoDB vector search error: %s", exc)
        # Fallback: text search
        return await search_articles(
            article_data.get("title", article_id), limit=limit
        )


@tool
def format_article_recommendation(
    article_id: str,
    title: str,
    excerpt: str,
    published_at: str,
    relevance_score: float,
) -> dict[str, Any]:
    """Format an article as a structured recommendation result.

    Args:
        article_id: The CMS article ID.
        title: Article title.
        excerpt: Short excerpt or summary.
        published_at: Publication date/time string.
        relevance_score: Similarity score (0.0–1.0).

    Returns:
        Dict with id, title, excerpt, published_at, relevance_score, relevance_label.
    """
    if relevance_score >= 0.85:
        label = "Highly relevant"
    elif relevance_score >= 0.70:
        label = "Relevant"
    elif relevance_score >= 0.50:
        label = "Somewhat relevant"
    else:
        label = "Loosely related"

    return {
        "id": article_id,
        "title": title,
        "excerpt": excerpt,
        "published_at": published_at,
        "relevance_score": round(relevance_score, 4),
        "relevance_label": label,
    }
