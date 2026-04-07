"""Column name resolution: maps natural language terms to DB column names.

This module is the single source of truth for the analytics schema.
It is imported by both the intent_parser (for whitelist validation) and
the analytics_agent (for system prompt generation).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical mapping: user-facing term → DB column name (documents table)
# ---------------------------------------------------------------------------
DATA_DICTIONARY: dict[str, str] = {
    # Reach
    "reach": "total_reach",
    "total reach": "total_reach",
    "organic reach": "organic_reach",
    "paid reach": "paid_reach",
    # Impressions
    "impressions": "total_impressions",
    "total impressions": "total_impressions",
    "organic impressions": "organic_impressions",
    "paid impressions": "paid_impressions",
    # Interactions / Reactions
    "interactions": "total_interactions",
    "total interactions": "total_interactions",
    "organic interactions": "organic_interactions",
    "reactions": "total_reactions",
    "total reactions": "total_reactions",
    # Engagement
    "engagements": "engagements",
    "engagement rate": "reach_engagement_rate",
    "reach engagement rate": "reach_engagement_rate",
    # Likes / Comments / Shares
    "likes": "total_likes",
    "total likes": "total_likes",
    "comments": "total_comments",
    "total comments": "total_comments",
    "shares": "total_shares",
    "total shares": "total_shares",
    # Video
    "video views": "video_views",
    "video views count": "video_views",
    "views": "video_views",
    "video view time": "total_video_view_time_sec",
    "total video view time": "total_video_view_time_sec",
    "avg video view time": "avg_video_view_time_sec",
    "avg. video view time": "avg_video_view_time_sec",
    "average video view time": "avg_video_view_time_sec",
    "completion rate": "completion_rate",
    # Dimensions
    "platform": "platform",
    "content type": "content_type",
    "media type": "media_type",
    "origin": "origin_of_the_content",
    "origin of content": "origin_of_the_content",
    "origin of the content": "origin_of_the_content",
    "profile name": "profile_name",
    "profile": "profile_name",
    "author": "author_name",
    "author name": "author_name",
    "date": "published_date",
    "published date": "published_date",
    "published time": "published_time",
    "labels": "labels",
    "tags": "labels",
}

# ---------------------------------------------------------------------------
# Whitelists derived from init.sql – the only columns the LLM may reference
# ---------------------------------------------------------------------------
WHITELISTED_METRICS: frozenset[str] = frozenset({
    "organic_reach",
    "paid_reach",
    "total_reach",
    "organic_impressions",
    "paid_impressions",
    "total_impressions",
    "organic_interactions",
    "total_interactions",
    "total_reactions",
    "total_comments",
    "total_shares",
    "engagements",
    "total_likes",
    "video_views",
    "total_video_view_time_sec",
    "avg_video_view_time_sec",
    "completion_rate",
    "reach_engagement_rate",
})

WHITELISTED_DIMENSIONS: frozenset[str] = frozenset({
    "platform",
    "content_type",
    "media_type",
    "origin_of_the_content",
    "profile_name",
    "author_name",
    "published_date",
    "labels",
})


def build_data_dictionary_prompt() -> str:
    """Return the DATA DICTIONARY section text for LLM system prompts."""
    metrics = sorted(WHITELISTED_METRICS)
    dims = sorted(WHITELISTED_DIMENSIONS)
    return (
        "### DATA DICTIONARY\n"
        "You MUST only reference the following column names from the `documents` table.\n"
        f"**Metrics**: {', '.join(f'`{m}`' for m in metrics)}\n"
        f"**Dimensions**: {', '.join(f'`{d}`' for d in dims)}\n"
    )


def resolve_column(user_term: str) -> str | None:
    """Map a natural-language term to its canonical DB column name.

    Args:
        user_term: Free-text term from user query (e.g. "views", "engagement rate").

    Returns:
        Canonical column name string, or None if no mapping is found.
    """
    return DATA_DICTIONARY.get(user_term.strip().lower())
