"""OpenAI Agents SDK function tools backed by SQL analytics queries.

These tools intentionally keep data access in the backend so the model cannot
run arbitrary SQL. The agent calls typed tools; the backend executes safe,
parameterized SQLAlchemy queries against the documents table.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from strands import tool
from sqlalchemy import and_, func, select

from app.config import settings
from app.db.session import AsyncSessionLocal
import logging
from app.schemas.document import Document

_logger = logging.getLogger(__name__)

def _parse_date(value: str | None) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


METRIC_COLUMNS: dict[str, Any] = {
    # Primary aliases (short names)
    "reach": Document.total_reach,
    "impressions": Document.total_impressions,
    "likes": Document.total_likes,
    "comments": Document.total_comments,
    "shares": Document.total_shares,
    "interactions": Document.total_interactions,
    "engagements": Document.engagements,
    "video_views": Document.video_views,
    "completion_rate": Document.completion_rate,
    # Full column-name aliases (match init.sql exactly)
    "total_reach": Document.total_reach,
    "organic_reach": Document.organic_reach,
    "paid_reach": Document.paid_reach,
    "total_impressions": Document.total_impressions,
    "organic_impressions": Document.organic_impressions,
    "paid_impressions": Document.paid_impressions,
    "total_interactions": Document.total_interactions,
    "organic_interactions": Document.organic_interactions,
    "total_reactions": Document.total_reactions,
    "reactions": Document.total_reactions,
    "total_comments": Document.total_comments,
    "total_shares": Document.total_shares,
    "total_likes": Document.total_likes,
    "reach_engagement_rate": Document.reach_engagement_rate,
    "engagement_rate": Document.reach_engagement_rate,
    "total_video_view_time_sec": Document.total_video_view_time_sec,
    "avg_video_view_time_sec": Document.avg_video_view_time_sec,
}


GROUP_BY_COLUMNS: dict[str, Any] = {
    "platform": Document.platform,
    "beast_uuid": Document.beast_uuid,
    "published_date": Document.published_date,
    "profile_id": Document.profile_id,
    "content_type": Document.content_type,
    "media_type": Document.media_type,
    # Additional dimensions
    "labels": Document.labels,
    "author_name": Document.author_name,
    "profile_name": Document.profile_name,
    "origin_of_content": Document.origin_of_the_content,
    "origin_of_the_content": Document.origin_of_the_content,
}


@tool
async def list_available_data_db() -> str:
    return await list_available_data_db_impl()


async def list_available_data_db_impl() -> str:
    """List dataset coverage in the SQL analytics store.

    Returns date range, row count, platforms, and metric names available for
    querying through SQL-backed analytics tools.
    """
    async with AsyncSessionLocal() as session:
        stats_stmt = select(
            func.count(Document.id),
            func.min(Document.published_date),
            func.max(Document.published_date),
        )
        stats_result = await session.execute(stats_stmt)
        total_rows, min_date, max_date = stats_result.one()

        platforms_stmt = select(Document.platform).where(Document.platform.is_not(None)).distinct()
        platforms_result = await session.execute(platforms_stmt)
        platforms = sorted({row[0] for row in platforms_result.fetchall() if row[0]})

    return json.dumps(
        {
            "source": "postgres.documents",
            "total_rows": int(total_rows or 0),
            "date_range": {
                "from": min_date.isoformat() if min_date else None,
                "to": max_date.isoformat() if max_date else None,
            },
            "platforms": platforms,
            "available_metrics": sorted(METRIC_COLUMNS.keys()),
            "group_by_dimensions": sorted(GROUP_BY_COLUMNS.keys()),
        }
    )


@tool
async def query_metrics_db(
    metric: str,
    aggregation: str = "sum",
    platform: str | None = None,
    profile_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: str | None = None,
    limit: int = settings.db_default_limit,
) -> str:
    return await query_metrics_db_impl(
        metric=metric,
        aggregation=aggregation,
        platform=platform,
        profile_id=profile_id,
        start_date=start_date,
        end_date=end_date,
        group_by=group_by,
        limit=limit,
    )


async def query_metrics_db_impl(
    metric: str,
    aggregation: str = "sum",
    platform: str | None = None,
    profile_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: str | None = None,
    limit: int = settings.db_default_limit,
) -> str:
    """Aggregate a metric from database records using safe SQL.

    Args:
        metric: One of available_metrics from list_available_data_db.
        aggregation: sum|avg|max|min|count
        platform: Optional platform filter.
        profile_id: Optional profile filter.
        start_date: Optional YYYY-MM-DD inclusive lower bound.
        end_date: Optional YYYY-MM-DD inclusive upper bound.
        group_by: Optional comma-separated dimensions from group_by_dimensions.
        limit: Max rows to return (bounded by configured DB row limits).
    """
    metric_key = (metric or "").strip().lower()
    metric_col = METRIC_COLUMNS.get(metric_key)
    if metric_col is None:
        return json.dumps(
            {
                "error": f"Unsupported metric '{metric}'",
                "allowed_metrics": sorted(METRIC_COLUMNS.keys()),
            }
        )

    agg_key = (aggregation or "sum").strip().lower()
    agg_map = {
        "sum": func.sum,
        "avg": func.avg,
        "max": func.max,
        "min": func.min,
        "count": func.count,
    }
    agg_fn = agg_map.get(agg_key)
    if agg_fn is None:
        return json.dumps({"error": f"Unsupported aggregation '{aggregation}'", "allowed": sorted(agg_map.keys())})

    bounded_limit = max(1, min(limit, settings.db_max_rows_per_query))
    start = _parse_date(start_date)
    end = _parse_date(end_date)

    group_dims: list[str] = []
    group_cols: list[Any] = []
    if group_by:
        for dim in [part.strip().lower() for part in group_by.split(",") if part.strip()]:
            col = GROUP_BY_COLUMNS.get(dim)
            if col is not None:
                group_dims.append(dim)
                group_cols.append(col)

    filters = []
    if platform:
        filters.append(func.lower(Document.platform) == platform.lower())
    if profile_id:
        filters.append(Document.profile_id == profile_id)
    if start:
        filters.append(Document.published_date >= start)
    if end:
        filters.append(Document.published_date <= end)

    value_col = agg_fn(metric_col).label("metric_value")
    stmt = select(*group_cols, value_col)
    if filters:
        stmt = stmt.where(and_(*filters))
    if group_cols:
        stmt = stmt.group_by(*group_cols)
    stmt = stmt.order_by(value_col.desc()).limit(bounded_limit)

    _logger.info(f"Executing SQL query {stmt}")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        raw_rows = result.fetchall()

    rows = []
    for raw in raw_rows:
        row_out: dict[str, Any] = {"value": _safe_float(raw[-1])}
        for idx, dim in enumerate(group_dims):
            dim_val = raw[idx]
            if hasattr(dim_val, "isoformat"):
                row_out[dim] = dim_val.isoformat()
            else:
                row_out[dim] = dim_val
        rows.append(row_out)

    return json.dumps(
        {
            "source": "postgres.documents",
            "metric": metric_key,
            "aggregation": agg_key,
            "filters": {
                "platform": platform,
                "profile_id": profile_id,
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
            },
            "group_by": group_dims,
            "rows": rows,
        }
    )


@tool
async def get_top_content_db(
    metric: str = "video_views",
    platform: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    keyword: str | None = None,
    limit: int = settings.db_default_limit,
) -> str:
    return await get_top_content_db_impl(
        metric=metric,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        limit=limit,
    )


async def get_top_content_db_impl(
    metric: str = "video_views",
    platform: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    keyword: str | None = None,
    limit: int = settings.db_default_limit,
) -> str:
    """Rank top content by a metric using SQL aggregation."""
    metric_key = (metric or "").strip().lower()
    metric_col = METRIC_COLUMNS.get(metric_key)
    if metric_col is None:
        return json.dumps(
            {
                "error": f"Unsupported metric '{metric}'",
                "allowed_metrics": sorted(METRIC_COLUMNS.keys()),
            }
        )

    bounded_limit = max(1, min(limit, settings.db_max_rows_per_query))
    start = _parse_date(start_date)
    end = _parse_date(end_date)

    filters = []
    if platform:
        filters.append(func.lower(Document.platform) == platform.lower())
    if start:
        filters.append(Document.published_date >= start)
    if end:
        filters.append(Document.published_date <= end)
    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            (Document.title.ilike(pattern))
            | (Document.content.ilike(pattern))
            | (Document.description.ilike(pattern))
        )

    value_col = func.sum(metric_col).label("metric_value")
    title_col = func.max(func.coalesce(Document.title, "")).label("title")
    content_col = func.max(Document.content).label("content")
    content_id_col = func.max(Document.content_id).label("content_id")
    stmt = select(
        Document.beast_uuid,
        title_col,
        content_col,
        content_id_col,
        value_col,
    )
    if filters:
        stmt = stmt.where(and_(*filters))
    stmt = (
        stmt.group_by(Document.beast_uuid)
        .order_by(value_col.desc())
        .limit(bounded_limit)
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        raw_rows = result.fetchall()

    rows = [
        {
            "beast_uuid": str(row[0]) if row[0] is not None else None,
            "title": row[1],
            "content": row[2],
            "content_id": row[3],
            "value": _safe_float(row[4]),
        }
        for row in raw_rows
    ]

    return json.dumps(
        {
            "source": "postgres.documents",
            "metric": metric_key,
            "rows": rows,
        }
    )


@tool
async def get_publishing_insights_db(
    platform: str | None = None,
    days: int = settings.publishing_insights_default_days,
) -> str:
    return await get_publishing_insights_db_impl(platform=platform, days=days)


async def get_publishing_insights_db_impl(
    platform: str | None = None,
    days: int = settings.publishing_insights_default_days,
) -> str:
    """Compute best publish day by average interactions from SQL data.

    If *platform* is None or 'all', aggregates across every platform.
    """
    bounded_days = max(settings.publishing_insights_min_days, min(days, settings.publishing_insights_max_days))
    start = date.today() - timedelta(days=bounded_days)

    day_label = func.to_char(Document.published_date, "Day").label("day_of_week")
    avg_eng = func.avg(func.coalesce(Document.total_interactions, 0)).label("avg_interactions")
    sample = func.count(Document.id).label("sample_size")

    conditions = [Document.published_date >= start]
    resolved_platform = (platform or "").strip().lower()
    if resolved_platform and resolved_platform != "all":
        conditions.append(func.lower(Document.platform) == resolved_platform)

    stmt = (
        select(day_label, avg_eng, sample)
        .where(and_(*conditions))
        .group_by(day_label)
        .order_by(avg_eng.desc())
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        raw_rows = result.fetchall()

    rows = [
        {
            "day_of_week": (row[0] or "").strip(),
            "avg_interactions": _safe_float(row[1]),
            "sample_size": int(row[2] or 0),
        }
        for row in raw_rows
    ]

    return json.dumps(
        {
            "source": "postgres.documents",
            "platform": resolved_platform or "all",
            "analysis_days": bounded_days,
            "rows": rows,
        }
    )


__all__ = [
    "list_available_data_db",
    "query_metrics_db",
    "get_top_content_db",
    "get_publishing_insights_db",
    "list_available_data_db_impl",
    "query_metrics_db_impl",
    "get_top_content_db_impl",
    "get_publishing_insights_db_impl",
]
