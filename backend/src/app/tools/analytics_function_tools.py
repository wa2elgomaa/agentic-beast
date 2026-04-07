"""OpenAI Agents SDK @function_tool definitions for Excel analytics data.

These tools give the analytics Agent direct access to the local Excel exports
in data/analytics/.  Each tool loads data through a shared in-process cache so
repeated calls within a run don't re-read the files from disk.

Available tools
---------------
list_available_data      – discover what files / date ranges are loaded
query_metrics            – aggregate a numeric metric with optional filters
get_top_content          – rank individual posts by a metric
get_publishing_insights  – find the best day/hour to publish
"""

from __future__ import annotations

import glob
import json
import os
import warnings
from functools import lru_cache
from typing import Optional

import pandas as pd
from strands import tool

from app.config import settings

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

# Resolve the analytics data folder relative to this source file so the tools
# work regardless of the process working directory.
_THIS_DIR = os.path.dirname(__file__)
_DATA_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "..", "..", "data", "analytics"))


@lru_cache(maxsize=1)
def _load_all_data() -> pd.DataFrame:
    """Load every .xlsx file in data/analytics/ into a single DataFrame.

    Results are cached for the lifetime of the process.  Call
    ``_load_all_data.cache_clear()`` to force a reload (e.g. after new files
    are dropped in).
    """
    pattern = os.path.join(_DATA_DIR, "*.xlsx")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for path in files:
        try:
            df = pd.read_excel(path, sheet_name="API", header=0)
            # Normalise column names: lowercase, spaces → underscores
            df.columns = [c.strip().lower().replace(" ", "_").replace("(", "").replace(")", "") for c in df.columns]
            # Suppress fragmentation warning — 133-col frames trigger it harmlessly
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
                df = df.assign(_source_file=os.path.basename(path))
            frames.append(df)
        except Exception:
            pass

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True).copy()

    # Coerce published_at to datetime and derive temporal columns in one shot
    if "published_at" in combined.columns:
        published = pd.to_datetime(combined["published_at"], errors="coerce", utc=True)
        combined = combined.assign(
            published_at=published,
            published_date=published.dt.date,
            day_of_week=published.dt.day_name(),
            hour=published.dt.hour,
            month=published.dt.tz_localize(None).dt.to_period("M").astype(str)
            if hasattr(published.dt, "tz_localize")
            else published.dt.to_period("M").astype(str),
        )

    return combined


def _numeric(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def _sanitize_text(text: object) -> str:
    """Normalize arbitrary text to a single printable line for JSON payloads."""
    if text is None:
        return ""

    cleaned = str(text).replace("\r", " ").replace("\n", " ")
    # Strip control characters that can break downstream parsing/rendering.
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch.isspace())
    return " ".join(cleaned.split())


def _safe_truncate(text: object, max_len: int) -> str:
    """Truncate normalized text without cutting surrogate/control sequences."""
    sanitized = _sanitize_text(text)
    if len(sanitized) <= max_len:
        return sanitized
    if max_len <= 3:
        return sanitized[:max_len]
    return sanitized[: max_len - 3].rstrip() + "..."


# ---------------------------------------------------------------------------
# Tool: list_available_data
# ---------------------------------------------------------------------------


def _list_available_data_impl() -> str:
    """List all analytics data files that are currently loaded and queryable.

    Returns a JSON object describing each file, its date range, row count,
    and the platforms it contains.  Call this first to know what data is
    available before constructing a metrics query.

    Returns:
        JSON string with keys: files (list of file summaries), total_rows,
        platforms (list), and columns (list of available metric columns).
    """
    df = _load_all_data()
    if df.empty:
        return json.dumps({"error": f"No Excel files found in {_DATA_DIR}"})

    metric_cols = [
        c for c in df.columns
        if any(kw in c for kw in [
            "view_count", "interactions", "reach", "impressions",
            "likes", "comments", "shares", "engagements", "completion",
        ])
    ]

    summaries = []
    for source, grp in df.groupby("_source_file"):
        info: dict = {"file": source, "rows": int(len(grp))}
        if "published_at" in grp.columns:
            valid = grp["published_at"].dropna()
            if not valid.empty:
                info["date_range"] = {
                    "from": str(valid.min().date()),
                    "to": str(valid.max().date()),
                }
        if "platform" in grp.columns:
            info["platforms"] = grp["platform"].dropna().unique().tolist()
        summaries.append(info)

    platforms = df["platform"].dropna().unique().tolist() if "platform" in df.columns else []
    content_types = df["content_type"].dropna().unique().tolist() if "content_type" in df.columns else []
    media_types = df["media_type"].dropna().unique().tolist() if "media_type" in df.columns else []

    # Per-platform breakdown of media_type values
    platform_media: dict = {}
    if "platform" in df.columns and "media_type" in df.columns:
        for plat, grp in df.groupby("platform"):
            platform_media[str(plat)] = grp["media_type"].dropna().unique().tolist()

    return json.dumps({
        "files": summaries,
        "total_rows": int(len(df)),
        "platforms": platforms,
        "content_types": content_types,
        "media_types": media_types,
        "platform_media_types": platform_media,
        "available_metric_columns": metric_cols,
        "filter_tip": "Use media_type (e.g. 'video','image','carousel') to filter by content format. Use content_type (e.g. 'post','story','collaboration','reply','shared') to filter by post category.",
    })


list_available_data = tool(_list_available_data_impl)


# ---------------------------------------------------------------------------
# Tool: query_metrics
# ---------------------------------------------------------------------------


def _query_metrics_impl(
    metric: str,
    platform: Optional[str] = None,
    content_type: Optional[str] = None,
    media_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: Optional[str] = None,
    top_n: int = settings.db_default_limit,
) -> str:
    """Aggregate a numeric metric from the analytics Excel data.

    Args:
        metric: Column name to aggregate, e.g. "video_view_count",
            "total_interactions", "organic_reach", "total_impressions".
            Use list_available_data to discover valid metric column names.
        platform: Filter to a single platform, e.g. "instagram", "facebook",
            "youtube", "tiktok", "twitter", "linkedin".  Omit for all platforms.
        content_type: Filter by post category: "post", "story", "collaboration",
            "reply", "shared".  Omit for all.
        media_type: Filter by content format: "video", "image", "carousel",
            "text".  Use this (not content_type) when the user asks about
            "videos" or "images".  Omit for all formats.
        start_date: Inclusive start date filter in YYYY-MM-DD format.
            Omit for no lower bound.
        end_date: Inclusive end date filter in YYYY-MM-DD format.
            Omit for no upper bound.
        group_by: Dimension to group results by.  One of: "platform",
            "content_type", "media_type", "day_of_week", "month".
            Omit to return a single aggregate total.
        top_n: Maximum number of rows to return when using group_by.

    Returns:
        JSON string with keys: metric, filters_applied, aggregation ("sum"),
        group_by, total (grand total), and rows (list of {label, value}).
    """
    df = _load_all_data()
    if df.empty:
        return json.dumps({"error": "No data loaded."})

    # Normalise metric name
    metric_norm = metric.strip().lower().replace(" ", "_")
    if metric_norm not in df.columns:
        close = [c for c in df.columns if metric_norm in c or c in metric_norm]
        return json.dumps({
            "error": f"Column '{metric_norm}' not found.",
            "suggestions": close[:5],
        })

    # Apply filters
    filtered = df.copy()
    filters: dict = {}

    if platform:
        filtered = filtered[filtered["platform"].str.lower() == platform.lower()]
        filters["platform"] = platform

    if content_type and "content_type" in filtered.columns:
        filtered = filtered[filtered["content_type"].str.lower() == content_type.lower()]
        filters["content_type"] = content_type

    if media_type and "media_type" in filtered.columns:
        filtered = filtered[filtered["media_type"].str.lower() == media_type.lower()]
        filters["media_type"] = media_type

    if start_date and "published_date" in filtered.columns:
        filtered = filtered[filtered["published_date"] >= pd.to_datetime(start_date).date()]
        filters["start_date"] = start_date

    if end_date and "published_date" in filtered.columns:
        filtered = filtered[filtered["published_date"] <= pd.to_datetime(end_date).date()]
        filters["end_date"] = end_date

    if filtered.empty:
        return json.dumps({"error": "No rows match the given filters.", "filters": filters})

    values = _numeric(filtered, metric_norm)
    grand_total = float(values.sum())
    top_n = max(1, min(top_n, settings.analytics_top_n_max))

    rows = []
    if group_by:
        gb_col = group_by.strip().lower()
        if gb_col not in filtered.columns:
            return json.dumps({"error": f"Cannot group by '{gb_col}'; column not found."})

        grouped = (
            filtered.groupby(gb_col)[metric_norm]
            .apply(lambda s: pd.to_numeric(s, errors="coerce").sum())
            .sort_values(ascending=False)
            .head(top_n)
        )
        rows = [{"label": str(k), "value": float(v)} for k, v in grouped.items()]

    return json.dumps({
        "metric": metric_norm,
        "filters_applied": filters,
        "aggregation": "sum",
        "group_by": group_by,
        "total": grand_total,
        "rows": rows,
    })


query_metrics = tool(_query_metrics_impl)


# ---------------------------------------------------------------------------
# Tool: get_top_content
# ---------------------------------------------------------------------------


def _get_top_content_impl(
    metric: str,
    platform: Optional[str] = None,
    content_type: Optional[str] = None,
    media_type: Optional[str] = None,
    keyword: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    top_n: int = settings.db_default_limit,
) -> str:
    """Return the top N individual posts ranked by a metric.

    Use this to answer questions like "what was our best performing video on
    TikTok last month?" or "top 5 Facebook posts by reach in February".

    Args:
        metric: Metric column to rank by, e.g. "video_view_count",
            "total_interactions", "organic_reach".
        platform: Filter to one platform, e.g. "tiktok", "instagram".
            Omit for all platforms.
        content_type: Filter by post category: "post", "story",
            "collaboration", "reply", "shared".  Omit for all.
        media_type: Filter by content format: "video", "image", "carousel",
            "text".  Use this (not content_type) when the user asks for
            "videos" or "images".  TikTok is entirely media_type='video'.
        keyword: Optional keyword to search for in the content/title text.
            Case-insensitive substring match.
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.
        top_n: Number of top posts to return (bounded by configured analytics limits).

    Returns:
        JSON string with a list of posts, each containing: rank, platform,
        content_type, published_at, metric_value, content_snippet, and
        post_detail_url.
    """
    df = _load_all_data()
    if df.empty:
        return json.dumps({"error": "No data loaded."})

    metric_norm = metric.strip().lower().replace(" ", "_")
    if metric_norm not in df.columns:
        close = [c for c in df.columns if metric_norm in c]
        return json.dumps({
            "error": f"Column '{metric_norm}' not found.",
            "suggestions": close[:5],
        })

    filtered = df.copy()

    if platform:
        filtered = filtered[filtered["platform"].str.lower() == platform.lower()]

    if content_type and "content_type" in filtered.columns:
        filtered = filtered[filtered["content_type"].str.lower() == content_type.lower()]

    if media_type and "media_type" in filtered.columns:
        filtered = filtered[filtered["media_type"].str.lower() == media_type.lower()]

    if keyword:
        mask = pd.Series(False, index=filtered.index)
        for col in ["content", "title", "description"]:
            if col in filtered.columns:
                mask = mask | filtered[col].fillna("").str.lower().str.contains(keyword.lower(), regex=False)
        filtered = filtered[mask]

    if start_date and "published_date" in filtered.columns:
        filtered = filtered[filtered["published_date"] >= pd.to_datetime(start_date).date()]

    if end_date and "published_date" in filtered.columns:
        filtered = filtered[filtered["published_date"] <= pd.to_datetime(end_date).date()]

    if filtered.empty:
        return json.dumps({"error": "No rows match the given filters."})

    top_n = max(1, min(top_n, settings.analytics_top_n_max))
    filtered = filtered.copy()
    filtered["_metric_val"] = _numeric(filtered, metric_norm)
    top = filtered.nlargest(top_n, "_metric_val")

    results = []
    for rank, (_, row) in enumerate(top.iterrows(), start=1):
        snippet = ""
        for col in ["title", "content", "description"]:
            val = row.get(col, "")
            if pd.notna(val) and str(val).strip():
                snippet = str(val)[:150].strip()
                break
        results.append({
            "rank": rank,
            "platform": _safe_truncate(row.get("platform", ""), 64),
            "content_type": _safe_truncate(row.get("content_type", ""), 64),
            "published_at": str(row.get("published_at", ""))[:19],
            metric_norm: float(row["_metric_val"]) if pd.notna(row["_metric_val"]) else 0,
            "title": _safe_truncate(row.get("title", ""), 240),
            # Keep content compact so the agent can always return valid schema JSON.
            "content": _safe_truncate(row.get("content", ""), 480),
            "content_snippet": _safe_truncate(snippet, 150),
            "post_detail_url": _safe_truncate(row.get("post_detail_url", ""), 500),
        })

    return json.dumps({
        "metric": metric_norm,
        "top_n": top_n,
        "results": results,
    })


get_top_content = tool(_get_top_content_impl)


# ---------------------------------------------------------------------------
# Tool: get_publishing_insights
# ---------------------------------------------------------------------------


def _get_publishing_insights_impl(
    platform: Optional[str] = None,
    metric: str = "video_view_count",
) -> str:
    """Find the best days and hours to publish content based on historical performance.

    Groups historical posts by day-of-week and by hour and computes the mean
    metric value for each bucket, providing actionable publishing time
    recommendations.

    Args:
        platform: Filter to a specific platform, e.g. "instagram", "tiktok",
            "youtube".  Omit to aggregate across all platforms.
        metric: The performance metric to optimise for, e.g.
            "video_view_count" (default), "total_interactions",
            "organic_reach".

    Returns:
        JSON string with: best_days (top 3 days of week with mean metric),
        best_hours (top 3 hours with mean metric), and sample_size.
    """
    df = _load_all_data()
    if df.empty:
        return json.dumps({"error": "No data loaded."})

    metric_norm = metric.strip().lower().replace(" ", "_")
    if metric_norm not in df.columns:
        return json.dumps({"error": f"Column '{metric_norm}' not found."})

    if "day_of_week" not in df.columns or "hour" not in df.columns:
        return json.dumps({"error": "Temporal columns not available."})

    filtered = df.copy()
    if platform:
        filtered = filtered[filtered["platform"].str.lower() == platform.lower()]

    filtered["_val"] = _numeric(filtered, metric_norm)
    filtered = filtered.dropna(subset=["_val", "day_of_week", "hour"])

    if filtered.empty:
        return json.dumps({"error": "No rows with valid data for the given filters."})

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    best_days = (
        filtered.groupby("day_of_week")["_val"]
        .mean()
        .reindex([d for d in day_order if d in filtered["day_of_week"].unique()])
        .sort_values(ascending=False)
        .head(3)
    )

    best_hours = (
        filtered.groupby("hour")["_val"]
        .mean()
        .sort_values(ascending=False)
        .head(3)
    )

    return json.dumps({
        "metric": metric_norm,
        "platform": platform or "all",
        "sample_size": int(len(filtered)),
        "best_days": [
            {"day": day, "mean_metric": round(float(val), 1)}
            for day, val in best_days.items()
        ],
        "best_hours_utc": [
            {"hour": int(h), "mean_metric": round(float(val), 1)}
            for h, val in best_hours.items()
        ],
    })


get_publishing_insights = tool(_get_publishing_insights_impl)
