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
        label = (
            _safe_str(row.get("day_of_week")).strip()
            or _safe_str(row.get("platform")).strip()
            or _display_label(row)
        )
        value = _numeric_value(row)
        # Ensure title falls back to the actual content when title is empty
        raw_title = (row.get("title") or "").strip()
        if raw_title:
            title_field = _safe_str(raw_title)
        else:
            # prefer the full content text, then content_id, then any display_label
            title_field = _safe_str(row.get("content") or row.get("content_id") or row.get("display_label"))

        result_data.append(
            {
                "label": label,
                "value": _safe_str(value),
                # Frontend AnalyticsResultDataItem fields
                "platform": _safe_str(row.get("platform")),
                "title": title_field,
                "content": _safe_str(row.get("content_id") or row.get("content")),
                "published_at": _safe_str(
                    row.get("published_date") or row.get("published_at")
                ),
                # Extra convenience field (frontend uses "views" for top-content cards)
                "views": _safe_str(row.get("video_views") or row.get("value") or ""),
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
    return {
        "query_type": query_category,
        "resolved_context": metric or query_category,
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
