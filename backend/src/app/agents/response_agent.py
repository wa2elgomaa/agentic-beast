"""Response Agent: map raw DB rows to the client AnalyticsResponseContent schema.

Contract:
- NEVER invent numeric values — all numbers come from *rows*.
- Narrative / insight_summary is derived deterministically from the rows.
- Produces the shape expected by the frontend AnalyticsResponseContent interface:
    query_type, resolved_context, result_data, insight_summary, verification

AnalyticsResultDataItem (frontend/types/index.ts):
    platform, content, title, published_at, views  (generic label/value added here)
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _display_label(row: dict[str, Any]) -> str:
    """Return title, display_label, or first 200 chars of content, or 'Unknown'."""
    for key in ("title", "display_label"):
        val = (row.get(key) or "").strip()
        if val:
            return val
    c = str(row.get("content") or "").strip()
    return c[:200] or "Unknown"


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _format_number(v: Any) -> str:
    """Format numeric values with thousands separators and no decimals when possible."""
    try:
        if v is None:
            return ""
        num = float(v)
    except (ValueError, TypeError):
        return _safe_str(v)

    # If effectively an integer, format without decimals
    if abs(num - int(num)) < 1e-9:
        return f"{int(num):,}"
    # Otherwise format with no fractional digits as well (UI prefers whole numbers)
    return f"{num:,.0f}"


def _build_view_url(platform: str | None, content_id: str | None) -> str:
    """Return a best-effort URL to view the content on its platform.

    Uses common platform URL patterns; falls back to a generic host if unknown.
    """
    if not content_id:
        return ""
    p = (platform or "").strip().lower()
    cid = str(content_id)
    if "youtube" in p or p == "youtube":
        return f"https://www.youtube.com/watch?v={cid}"
    if "tiktok" in p or p == "tiktok":
        return f"https://www.tiktok.com/t/{cid}"
    if "instagram" in p or p == "instagram":
        return f"https://www.instagram.com/p/{cid}"
    if "facebook" in p or p == "facebook":
        return f"https://www.facebook.com/{cid}"
    # Generic fallback
    return f"https://{p or 'content'}.example/{cid}"


def _numeric_value(row: dict[str, Any]) -> float:
    """Extract the primary numeric value from a row (handles varied column names)."""
    for key in ("metric_value", "value", "avg_interactions", "total", "count"):
        v = row.get(key)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_analytics_response(
    rows: list[dict[str, Any]],
    original_message: str,
    metric: str | None = None,
    operation: str = "sum",
    query_category: str = "metrics",
    attempted_sqls: list[str] | None = None,
) -> dict[str, Any]:
    """Map raw DB rows to the AnalyticsResponseContent frontend schema.

    Args:
        rows:             Raw dicts from ``execute_safe_sql`` / DB *_impl tools.
        original_message: The user's original natural-language query.
        metric:           Resolved metric name (snake_case) or None.
        operation:        SQL operation: sum | average | top_n | compare | …
        query_category:   metrics | publishing_insights | compare
        attempted_sqls:   List of SQL statements tried (for verification note).

    Returns:
        Dict matching ``AnalyticsResponseContent``:
        ``{query_type, resolved_context, result_data, insight_summary, verification}``
    """
    metric_label = (metric or "data").replace("_", " ").title()
    sqls_note = f" ({len(attempted_sqls)} SQL attempt(s) made)" if attempted_sqls else ""

    # ------------------------------------------------------------------
    # result_data — one item per row, mapped to frontend shape
    # ------------------------------------------------------------------
    result_data: list[dict[str, Any]] = []
    for row in rows:
        # Display label: day_of_week (insights), platform (compare), otherwise title/content
        # Prefer content/title label for top-item cards; fall back to platform for compare rows.
        display_label = _display_label(row)
        label = (
            _safe_str(row.get("day_of_week")).strip()
            or (display_label if display_label != "Unknown" else "")
            or _safe_str(row.get("platform")).strip()
            or "Unknown"
        )

        # Primary numeric value (ensure formatted for UI)
        numeric = _numeric_value(row)
        formatted_value = _format_number(numeric)

        # Title should be title column first, then content column.
        raw_title = (row.get("title") or "").strip()
        if raw_title:
            title_field = _safe_str(raw_title)
        else:
            title_field = _safe_str(row.get("content") or "")

        # Content/description should map to content column (not content_id).
        content_field = _safe_str(row.get("content") or "")

        # View link for platform (best-effort)
        view_url = _build_view_url(_safe_str(row.get("platform")), row.get("content_id"))

        result_data.append(
            {
                "label": label,
                "value": formatted_value,
                # Frontend AnalyticsResultDataItem fields
                "platform": _safe_str(row.get("platform")),
                "title": title_field,
                # keep `content` for backwards compatibility and add description alias
                "content": content_field,
                "description": content_field,
                "view_url": view_url,
                "published_at": _safe_str(
                    row.get("published_date") or row.get("published_at")
                ),
                # Extra convenience field (frontend uses "views" for top-content cards)
                "views": _format_number(row.get("video_views") or row.get("value") or numeric),
            }
        )
    # ------------------------------------------------------------------
    # insight_summary — deterministic text from real values (no LLM numbers)
    # ------------------------------------------------------------------
    if not rows:
        insight = (
            f"No data found for {metric_label!r}. "
            "Try broadening the time window or removing filters."
        )

    elif query_category == "publishing_insights" or any(
        "day_of_week" in r for r in rows[:1]
    ):
        lines = []
        for r in rows[:7]:
            day = _safe_str(r.get("day_of_week") or r.get("label") or "?").strip()
            avg = _numeric_value(r)
            sample = r.get("sample_size") or r.get("count") or ""
            suffix = f" ({sample} posts)" if sample else ""
            lines.append(f"  {day}: avg {avg:,.0f} interactions{suffix}")
        insight = "Best days to publish (by avg interactions):\n" + "\n".join(lines)

    elif operation in ("top_n", "compare") or query_category == "compare":
        lines = []
        for i, (r, rd) in enumerate(zip(rows[:10], result_data[:10]), 1):
            lab = rd["label"] or "?"
            val = _numeric_value(r)
            plat = r.get("platform", "")
            suffix = f" — {plat}" if plat and plat.lower() != lab.lower() else ""
            lines.append(f"{i}. {lab}{suffix}: {val:,.0f}")
        op_label = "Platform comparison" if query_category == "compare" else f"Top {len(rows)}"
        insight = f"{op_label} — {metric_label}:\n" + "\n".join(lines)

    else:
        total = sum(_numeric_value(r) for r in rows)
        insight = (
            f"{metric_label}: {total:,.0f} total across {len(rows)} group(s)."
        )

    # ------------------------------------------------------------------
    # Final response dict
    # ------------------------------------------------------------------
    resolved_subject = metric or query_category

    return {
        "query_type": query_category,
        # Keep both keys for backward compatibility across call sites.
        "resolved_subject": resolved_subject,
        "resolved_context": resolved_subject,
        "result_data": result_data,
        "insight_summary": insight,
        "verification": (
            f"All numeric values sourced directly from PostgreSQL — "
            f"no LLM-generated numbers.{sqls_note}"
        ),
    }


def build_error_response(
    reason: str,
    attempted_sqls: list[str] | None = None,
) -> dict[str, Any]:
    """Build a safe user-facing error response."""
    sqls_attempted = len(attempted_sqls or [])
    return {
        "query_type": "error",
        # Keep both keys for backward compatibility across call sites.
        "resolved_subject": "query_failed",
        "resolved_context": "query_failed",
        "result_data": [],
        "insight_summary": (
            "I couldn't generate a valid query for your request. "
            "Please try rephrasing — for example, specify a platform, metric, or time range."
        ),
        "verification": (
            f"Query failed after {sqls_attempted} attempt(s). "
            f"Reason: {reason}"
        ),
    }
