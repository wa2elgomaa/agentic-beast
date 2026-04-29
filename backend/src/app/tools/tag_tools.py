"""Tag matching tools for semantic tag suggestion.

Provides:
- find_similar_tags: vector similarity search against tags table
- rank_tags_by_relevance: combine semantic + keyword scores
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, text
from strands import tool

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _keyword_overlap_score(content: str, tag_name: str, variations: list[str]) -> float:
    """Compute a simple keyword overlap score (0.0–1.0).

    Checks whether the tag name or any of its variations appear as whole words
    in the article content (case-insensitive).
    """
    content_lower = content.lower()
    candidates = [tag_name.lower()] + [v.lower() for v in (variations or [])]
    hits = sum(1 for c in candidates if c and c in content_lower)
    return min(hits / max(len(candidates), 1), 1.0)


# ---------------------------------------------------------------------------
# Strands tools
# ---------------------------------------------------------------------------

@tool
async def find_similar_tags(
    article_content: str | None = None,
    article_embedding: list[float] | None = None,
    top_n: int = 10,
    exclude_ids: list[str] | None = None,
) -> str:
    """Find semantically similar tags for article content or embedding (Phase 2).

    Supports two input modes:
    1. article_content (str) — generates embedding on-the-fly
    2. article_embedding (list[float]) — uses pre-computed embedding

    Can exclude specific tag slugs from results (support for "show more" flow).

    Args:
        article_content: Article title/body text; if provided, generates embedding.
        article_embedding: Pre-computed 384-dim embedding; if provided, uses directly.
        top_n: Maximum number of tags to return (default 10, max 50).
        exclude_ids: List of tag slugs to exclude from results (optional).

    Returns:
        JSON string with list of matching tags including slug, name, description,
        similarity_score, and keyword_score.
    """
    import json

    top_n = min(top_n, 50)
    exclude_ids = exclude_ids or []

    # Validate that one of article_content or article_embedding is provided
    if not article_content and not article_embedding:
        return json.dumps({"error": "Either article_content or article_embedding is required", "tags": []})

    # 1. Get embedding (either pre-computed or generate from content)
    if article_embedding:
        embedding = article_embedding
        content_for_keywords = article_content or ""
    else:
        if not article_content.strip():
            return json.dumps({"error": "article_content is required when article_embedding not provided", "tags": []})

        try:
            from app.services.embedding_service import EmbeddingService

            embedding_svc = EmbeddingService()
            embedding = embedding_svc.embed_text(article_content[:2000])
            content_for_keywords = article_content
        except Exception as exc:
            _logger.error("Embedding generation failed: %s", exc)
            return json.dumps({"error": f"Embedding failed: {exc}", "tags": []})

    # 2. Vector similarity search via pgvector cosine distance
    try:
        from app.db.session import AsyncSessionLocal

        # Build embedding as a literal array string for pgvector
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        async with AsyncSessionLocal() as session:
            # Cosine similarity = 1 - cosine_distance
            query_sql = """
                SELECT
                    slug,
                    name,
                    description,
                    variations,
                    is_primary,
                    1 - (embedding <=> :emb::vector) AS similarity_score
                FROM tags
                WHERE embedding IS NOT NULL
            """
            
            # Add exclude list filter
            if exclude_ids:
                placeholders = ", ".join([f"'{slug}'" for slug in exclude_ids])
                query_sql += f" AND slug NOT IN ({placeholders})"
            
            query_sql += """
                ORDER BY embedding <=> :emb::vector
                LIMIT :limit
            """

            result = await session.execute(
                text(query_sql),
                {"emb": embedding_str, "limit": top_n},
            )
            rows = result.fetchall()

        tags = []
        for row in rows:
            variations = row.variations if isinstance(row.variations, list) else []
            kw_score = _keyword_overlap_score(content_for_keywords, row.name, variations)
            tags.append({
                "slug": row.slug,
                "name": row.name,
                "description": row.description or "",
                "variations": variations,
                "is_primary": bool(row.is_primary),
                "similarity_score": round(float(row.similarity_score or 0.0), 4),
                "keyword_score": round(kw_score, 4),
                "tag_id": row.slug,  # For exclude_ids tracking
            })

        return json.dumps({"tags": tags, "count": len(tags)})

    except Exception as exc:
        _logger.error("Tag similarity search failed: %s", exc)
        return json.dumps({"error": str(exc), "tags": []})


@tool
async def rank_tags_by_relevance(
    article_content: str,
    candidate_tags_json: str,
    top_n: int = 5,
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> str:
    """Rank candidate tags by combined semantic similarity and keyword overlap.

    Takes the JSON output from ``find_similar_tags`` and re-ranks by a weighted
    combination of semantic similarity and keyword match scores.

    Args:
        article_content: The article title and/or body text.
        candidate_tags_json: JSON string output from find_similar_tags (must
            include a "tags" list with similarity_score and keyword_score fields).
        top_n: Number of top-ranked tags to return (default 5, max 50).
        semantic_weight: Weight for semantic similarity score (default 0.7).
        keyword_weight: Weight for keyword overlap score (default 0.3).

    Returns:
        JSON string with ranked list of tags including final combined_score and rank.
    """
    import json

    top_n = min(top_n, 50)

    try:
        data = json.loads(candidate_tags_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid candidate_tags_json: {exc}", "tags": []})

    if "error" in data:
        return candidate_tags_json  # propagate upstream error

    candidates: list[dict[str, Any]] = data.get("tags", [])
    if not candidates:
        return json.dumps({"tags": [], "count": 0})

    # Ensure keyword scores are present (re-compute if missing)
    for tag in candidates:
        if "keyword_score" not in tag:
            variations = tag.get("variations") or []
            tag["keyword_score"] = _keyword_overlap_score(
                article_content, tag.get("name", ""), variations
            )

    # Compute combined score
    for tag in candidates:
        sem = float(tag.get("similarity_score") or 0.0)
        kw = float(tag.get("keyword_score") or 0.0)
        tag["combined_score"] = round(
            semantic_weight * sem + keyword_weight * kw, 4
        )

    # Sort descending by combined_score then by is_primary as tiebreaker
    ranked = sorted(
        candidates,
        key=lambda t: (t["combined_score"], int(t.get("is_primary", False))),
        reverse=True,
    )[:top_n]

    # Add rank field
    for i, tag in enumerate(ranked, start=1):
        tag["rank"] = i

    return json.dumps({
        "tags": ranked,
        "count": len(ranked),
        "semantic_weight": semantic_weight,
        "keyword_weight": keyword_weight,
    })
