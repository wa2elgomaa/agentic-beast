"""Context resolver — answer follow-up questions from prior conversation data.

When a user asks a simple aggregation or count question about data that was
already returned in a previous turn (e.g. "sum the page views", "how many
results were there?"), we can compute the answer directly from the stored
``prior_rows`` without routing to the analytics agent or hitting the database.

The resolver is intentionally conservative: it only short-circuits when the
query is clearly a numeric aggregation AND ``prior_rows`` exist in history.
Ambiguous or complex follow-ups fall through to the agent as normal.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Keyword patterns
# ---------------------------------------------------------------------------

_AGGREGATION_RE = re.compile(
    r"\b("
    r"sum|total|add(\s+up)?|aggregate|"
    r"average|avg|mean|"
    r"max(imum)?|highest|most|"
    r"min(imum)?|lowest|least|"
    r"count|how\s+many|how\s+much|"
    r"(from|of|in)\s+the\s+(above|these|those|this|previous|prior|last)(\s+(results?|rows?|data|list))?"
    r")\b",
    re.IGNORECASE,
)

# Metric field hints — maps keyword → possible field name substrings
_FIELD_HINTS: Dict[str, List[str]] = {
    "view": ["view", "views", "watch", "play"],
    "impression": ["impression", "impressions", "exposure"],
    "like": ["like", "likes", "heart", "reaction"],
    "comment": ["comment", "comments", "reply", "replies"],
    "share": ["share", "shares", "repost", "retweet"],
    "engagement": ["engagement", "interact", "interac", "engag"],
    "reach": ["reach", "unique"],
    "metric_value": ["metric", "value", "score", "count"],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def try_resolve_from_context(
    message: str,
    conversation_history: List[Dict[str, Any]],
) -> Optional[str]:
    """Try to answer *message* using data already present in *conversation_history*.

    Returns a human-readable answer string when the question can be resolved
    from prior data, or ``None`` to indicate the agent should handle it.
    """
    if not conversation_history:
        return None

    if not _AGGREGATION_RE.search(message):
        return None

    prior_rows = _get_latest_prior_rows(conversation_history)
    if not prior_rows:
        return None

    return _compute_aggregation(message, prior_rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_latest_prior_rows(history: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Find the most recent non-empty prior_rows list in conversation history."""
    for turn in reversed(history):
        rows = turn.get("prior_rows")
        if rows and isinstance(rows, list):
            return rows
    return None


def _compute_aggregation(message: str, rows: List[Dict[str, Any]]) -> Optional[str]:
    """Compute a simple numeric aggregation from *rows* based on *message*."""
    msg = message.lower()

    # --- Count ---
    if re.search(r"\bhow\s+many\b|\bcount\b|\bnumber\s+of\b", msg):
        return f"There are **{len(rows)}** results in the previous query."

    # Identify numeric fields
    numeric_fields = _collect_numeric_fields(rows)
    if not numeric_fields:
        return None

    target = _detect_target_field(msg, numeric_fields)
    if not target:
        return None

    values = [_safe_float(r.get(target, 0)) for r in rows]
    label = target.replace("_", " ")

    # --- Sum / total ---
    if re.search(r"\bsum\b|\btotal\b|\badd(\s+up)?\b|\baggregate\b", msg):
        total = sum(values)
        return (
            f"The total **{label}** across the {len(rows)} results is **{total:,.0f}**."
        )

    # --- Average ---
    if re.search(r"\baverage\b|\bavg\b|\bmean\b", msg):
        avg = sum(values) / len(values) if values else 0
        return (
            f"The average **{label}** across the {len(rows)} results is **{avg:,.1f}**."
        )

    # --- Max ---
    if re.search(r"\bmax(imum)?\b|\bhighest\b|\bmost\b", msg):
        max_row = max(rows, key=lambda r: _safe_float(r.get(target, 0)))
        max_val = _safe_float(max_row.get(target, 0))
        title = _row_title(max_row)
        suffix = f" ({title})" if title else ""
        return f"The highest **{label}** is **{max_val:,.0f}**{suffix}."

    # --- Min ---
    if re.search(r"\bmin(imum)?\b|\blowest\b|\bleast\b", msg):
        min_row = min(rows, key=lambda r: _safe_float(r.get(target, 0)))
        min_val = _safe_float(min_row.get(target, 0))
        title = _row_title(min_row)
        suffix = f" ({title})" if title else ""
        return f"The lowest **{label}** is **{min_val:,.0f}**{suffix}."

    return None


def _collect_numeric_fields(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Return {field_name: occurrence_count} for numeric fields across all rows."""
    counts: Dict[str, int] = {}
    for row in rows:
        for key, val in row.items():
            try:
                float(str(val).replace(",", ""))
                counts[key] = counts.get(key, 0) + 1
            except (ValueError, TypeError):
                pass
    return counts


def _detect_target_field(msg: str, field_counts: Dict[str, int]) -> Optional[str]:
    """Pick the most likely numeric field based on keywords in *msg*."""
    for hint_key, hints in _FIELD_HINTS.items():
        for hint in hints:
            if hint in msg:
                for actual_field in field_counts:
                    if hint_key in actual_field.lower() or any(
                        h in actual_field.lower() for h in hints
                    ):
                        return actual_field

    # Fallback: the most-commonly populated numeric field
    return max(field_counts, key=lambda k: field_counts[k]) if field_counts else None


def _row_title(row: Dict[str, Any]) -> str:
    for key in ("title", "content", "label", "name"):
        val = row.get(key)
        if val and isinstance(val, str):
            return val[:80]
    return ""


def _safe_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
