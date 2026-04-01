"""Structured query parser: converts a user message → StructuredQueryObject.

Uses Ollama's ``format=json`` constraint so the model is *forced* to emit
valid JSON, eliminating free-text hallucinations at the parse stage.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.nlp.column_mapper import WHITELISTED_METRICS, WHITELISTED_DIMENSIONS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt injected into every parse request
# ---------------------------------------------------------------------------

from datetime import date as _date  # noqa: PLC0415 — module-level for prompt construction

_METRICS_STR = ", ".join(sorted(WHITELISTED_METRICS))
_DIMS_STR = ", ".join(sorted(WHITELISTED_DIMENSIONS))
_TODAY = _date.today().isoformat()

_PARSE_SYSTEM_PROMPT = (
    "You are an analytics query parser. "
    "Your ONLY output is a raw JSON object — no markdown, no explanation.\n\n"
    "Output schema (all fields required):\n"
    "{\n"
    '  "query_category": "<metrics | publishing_insights | compare>",\n'
    '  "metric": "<whitelisted metric name or null>",\n'
    '  "operation": "<sum | average | max | min | top_n | count | compare>",\n'
    '  "group_by": "<whitelisted dimension or null>",\n'
    '  "filters": {"<dimension>": "<value>"},\n'
    '  "time_window": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"} or null,\n'
    '  "top_n": <integer or null>,\n'
    '  "keyword": "<free-text search term or null>"\n'
    "}\n\n"
    f"Whitelisted metrics: {_METRICS_STR}\n\n"
    f"Whitelisted dimensions: {_DIMS_STR}\n\n"
    "Rules:\n"
    "- For 'top N' or 'best N' requests: operation='top_n', top_n=N, query_category='metrics'.\n"
    "- For best posting time / when to publish: query_category='publishing_insights', metric=null.\n"
    "- For comparing platforms: query_category='compare', group_by='platform', operation='sum'.\n"
    "- For keyword/person/topic filtering (e.g. 'featuring X', 'about Y'): set keyword=<term>.\n"
    "- If metric not in whitelist, set metric=null.\n"
    f"- Today's date is {_TODAY}. All dates ISO 8601 (YYYY-MM-DD). 'last month' = previous calendar month relative to today.\n"
    "- Map 'average' → 'average', 'total'/'sum' → 'sum'.\n"
    "- IMPORTANT: When the user asks for top N items (e.g. 'give me top 3', 'show top 5'), ALWAYS set operation='top_n' and top_n=N.\n"
    "- Use prior conversation to resolve pronouns like 'them', 'those', 'it'.\n"
    "- Empty filters → {}.  Do NOT add keys outside the schema."
)

# ---------------------------------------------------------------------------
# Few-shot examples appended to every request to anchor output format
# ---------------------------------------------------------------------------

_FEW_SHOT: list[dict] = [
    {
        "role": "user",
        "content": "What was the total organic reach on Instagram last month?",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "query_category": "metrics",
            "metric": "organic_reach",
            "operation": "sum",
            "group_by": None,
            "filters": {"platform": "Instagram"},
            "time_window": {"from": "2026-02-01", "to": "2026-02-28"},
            "top_n": None,
            "keyword": None,
        }),
    },
    {
        "role": "user",
        "content": "Show me the top 5 videos by view count.",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "query_category": "metrics",
            "metric": "video_views",
            "operation": "top_n",
            "group_by": None,
            "filters": {},
            "time_window": None,
            "top_n": 5,
            "keyword": None,
        }),
    },
    {
        "role": "user",
        "content": "When should I post on Instagram?",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "query_category": "publishing_insights",
            "metric": None,
            "operation": "average",
            "group_by": None,
            "filters": {"platform": "Instagram"},
            "time_window": None,
            "top_n": None,
            "keyword": None,
        }),
    },
    {
        "role": "user",
        "content": "What are the best days to publish during the week?",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "query_category": "publishing_insights",
            "metric": None,
            "operation": "average",
            "group_by": None,
            "filters": {},
            "time_window": None,
            "top_n": None,
            "keyword": None,
        }),
    },
    {
        "role": "user",
        "content": "Give me top 3 videos featuring Donald Trump last month.",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "query_category": "metrics",
            "metric": "video_views",
            "operation": "top_n",
            "group_by": None,
            "filters": {},
            "time_window": {"from": "2026-03-01", "to": "2026-03-31"},
            "top_n": 3,
            "keyword": "Donald Trump",
        }),
    },
    {
        "role": "user",
        "content": "Compare total reach on Instagram and TikTok.",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "query_category": "compare",
            "metric": "total_reach",
            "operation": "compare",
            "group_by": "platform",
            "filters": {},
            "time_window": None,
            "top_n": None,
            "keyword": None,
        }),
    },
    {
        "role": "user",
        "content": "Average engagement rate for LinkedIn posts tagged Product?",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "query_category": "metrics",
            "metric": "reach_engagement_rate",
            "operation": "average",
            "group_by": None,
            "filters": {"platform": "LinkedIn", "labels": "Product"},
            "time_window": None,
            "top_n": None,
            "keyword": None,
        }),
    },
]


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class StructuredQueryObject(BaseModel):
    """Typed representation of a parsed analytics query."""

    query_category: str = "metrics"
    metric: Optional[str] = None
    operation: str = "sum"
    group_by: Optional[str] = None
    filters: dict = Field(default_factory=dict)
    time_window: Optional[dict] = None
    top_n: Optional[int] = None
    keyword: Optional[str] = None

    @field_validator("top_n", mode="before")
    @classmethod
    def validate_top_n(cls, v) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @field_validator("query_category", mode="before")
    @classmethod
    def validate_query_category(cls, v) -> str:
        allowed = {"metrics", "publishing_insights", "compare"}
        if isinstance(v, str) and v.lower() in allowed:
            return v.lower()
        return "metrics"

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in WHITELISTED_METRICS:
            logger.warning("parse_query: rejecting non-whitelisted metric", extra={"metric": v})
            return None
        return v

    @field_validator("operation", mode="before")
    @classmethod
    def validate_operation(cls, v) -> str:
        if not isinstance(v, str):
            return "sum"
        allowed = {"sum", "average", "max", "min", "top_n", "count", "compare"}
        return v.lower() if v.lower() in allowed else "sum"

    @field_validator("group_by", mode="before")
    @classmethod
    def validate_group_by(cls, v) -> Optional[str]:
        # Model sometimes returns a list — take the first element
        if isinstance(v, list):
            v = v[0] if v else None
        if not isinstance(v, str):
            return None
        if v not in WHITELISTED_DIMENSIONS:
            logger.warning("parse_query: rejecting non-whitelisted dimension", extra={"dimension": v})
            return None
        return v

    @field_validator("filters", mode="before")
    @classmethod
    def validate_filters(cls, v) -> dict:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        if not isinstance(v, dict):
            return {}
        # Normalise plural/alternate keys the LLM sometimes emits
        normalised = {}
        for k, val in v.items():
            key = k.lower().strip()
            # "platforms" → "platform", "content_types" → "content_type", etc.
            if key.endswith("s") and key[:-1] in {"platform", "content_type", "media_type", "label"}:
                key = key[:-1]
            # Unwrap single-item lists (LLM sometimes returns ["TikTok"] instead of "TikTok")
            if isinstance(val, list):
                val = val[0] if val else None
            normalised[key] = val
        return normalised

    @field_validator("time_window", mode="before")
    @classmethod
    def validate_time_window(cls, v) -> Optional[dict]:
        if v is None:
            return None
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, ValueError):
                return None
        if not isinstance(v, dict):
            return None
        # Ensure from/to values are strings (model sometimes returns null)
        cleaned = {}
        for k in ("from", "to"):
            val = v.get(k)
            cleaned[k] = val if isinstance(val, str) else None
        return cleaned if any(cleaned.values()) else None


class UnsupportedQueryError(Exception):
    """Raised when the query cannot be parsed or metric is unsupported."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def parse_query(
    message: str,
    conversation_history: list[dict] | None = None,
) -> StructuredQueryObject:
    """Parse a natural language analytics query into a StructuredQueryObject.

    Sends the message to Ollama with ``format=json`` to guarantee valid JSON
    output. Validates the result against WHITELISTED_METRICS.

    Args:
        message: User's natural language query.
        conversation_history: Optional prior messages [{role, content}] to resolve
            follow-up pronouns (e.g. "them", "those").

    Returns:
        StructuredQueryObject with parsed parameters.

    Raises:
        UnsupportedQueryError: If Ollama is unreachable or returns invalid JSON.
    """
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    # Build message list: system + few-shot + optional history + current query
    messages: list[dict] = [
        {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
        *_FEW_SHOT,
    ]
    if conversation_history:
        for h in conversation_history:
            role = h.get("role", "user")
            content = h.get("content", "")
            # Summarise long assistant JSON responses to avoid token overflow
            if role == "assistant" and len(str(content)) > 500:
                content = str(content)[:500] + "..."
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": message})

    payload = {
        "model": settings.ollama_model,
        "format": "json",
        "stream": False,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("parse_query: Ollama HTTP error", extra={"error": str(exc)})
        raise UnsupportedQueryError(f"Ollama returned HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        logger.error("parse_query: Ollama unreachable", extra={"error": str(exc)})
        raise UnsupportedQueryError(f"Ollama unreachable: {exc}") from exc

    raw_content = data.get("message", {}).get("content", "{}")
    try:
        parsed_dict = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        logger.error("parse_query: non-JSON from Ollama", extra={"raw": raw_content[:200]})
        raise UnsupportedQueryError("Ollama returned non-JSON content") from exc

    return StructuredQueryObject.model_validate(parsed_dict)
