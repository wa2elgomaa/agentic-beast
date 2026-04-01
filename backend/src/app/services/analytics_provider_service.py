"""Provider-agnostic analytics execution service.

For OpenAI, analytics runs through the OpenAI Agents SDK analytics agent.
For non-OpenAI providers (e.g. Ollama), this service performs a two-step flow:
1) Plan the tool call from user text.
2) Execute SQL-backed analytics tool and synthesize final JSON response.
"""

from __future__ import annotations

import json
from typing import Any

from app.logging import get_logger
from app.providers import get_ai_provider
from app.providers.base import Message
from app.services.provider_payload_validation import validate_provider_payload
from app.tools.analytics_db_function_tools import (
    get_publishing_insights_db_impl,
    get_top_content_db_impl,
    list_available_data_db_impl,
    query_metrics_db_impl,
)

logger = get_logger(__name__)

_ALLOWED_TOOLS = {
    "list_available_data_db",
    "query_metrics_db",
    "get_top_content_db",
    "get_publishing_insights_db",
}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return None

    return None


async def _execute_planned_tool(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "list_available_data_db":
        return await list_available_data_db_impl()

    if tool_name == "query_metrics_db":
        metric_arg = str(args.get("metric", "reach"))
        return await query_metrics_db_impl(
            metric=metric_arg,
            aggregation=str(args.get("aggregation", "sum")),
            platform=args.get("platform"),
            profile_id=args.get("profile_id"),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            group_by=args.get("group_by"),
            limit=int(args.get("limit", 20)),
        )

    if tool_name == "get_top_content_db":
        metric_arg = str(args.get("metric", "video_views"))
        return await get_top_content_db_impl(
            metric=metric_arg,
            platform=args.get("platform"),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            keyword=args.get("keyword"),
            limit=int(args.get("limit", 10)),
        )

    if tool_name == "get_publishing_insights_db":
        return await get_publishing_insights_db_impl(
            platform=str(args.get("platform", "instagram")),
            days=int(args.get("days", 90)),
        )

    raise ValueError(f"Unsupported tool '{tool_name}'")


async def execute_analytics_with_provider(message: str) -> dict[str, Any]:
    """Execute analytics query using configured non-OpenAI provider.

    Returns a normalized JSON object compatible with chat response handling.
    """
    provider = get_ai_provider()

    planner_system = (
        "You are an analytics query planner. "
        "Choose exactly one SQL analytics tool and arguments for the user question. "
        "Return ONLY valid JSON with keys: tool, args, query_type. "
        "Allowed tools: list_available_data_db, query_metrics_db, get_top_content_db, get_publishing_insights_db. "
        "CRITICAL: Use only the following metric column names when setting the `metric` argument: \n"
        "['comments', 'completion_rate', 'engagements', 'impressions', 'interactions', 'likes', 'reach', 'shares', 'video_views']\n"
        "For `query_metrics_db` args may include: metric (one of the allowed names above), aggregation, platform, profile_id, start_date, end_date, group_by, limit. "
        "For `get_top_content_db` args may include: metric (one of the allowed names above), platform, start_date, end_date, keyword, limit. "
        "For `get_publishing_insights_db` args: platform, days. "
        "If the user's wording uses synonyms (e.g., 'views', 'view_count', 'likes_count'), map them internally to the nearest allowed metric but RETURN the allowed metric name in the JSON `args.metric` field — do NOT invent new metric names. "
        "If you cannot confidently map a requested metric to one of the allowed names, set `args.metric` to 'reach' and include a short explanation in `args._note` describing ambiguity."
    )

    plan_resp = await provider.complete_with_retry(
        messages=[
            Message(role="system", content=planner_system),
            Message(role="user", content=message),
        ],
        temperature=0.1,
        max_tokens=300,
    )

    plan = _extract_json_object(plan_resp.content or "") or {}
    tool_name = str(plan.get("tool", "")).strip()
    args = plan.get("args", {}) if isinstance(plan.get("args"), dict) else {}
    query_type = str(plan.get("query_type", "analytics") or "analytics")

    if tool_name not in _ALLOWED_TOOLS:
        logger.warning("Planner returned invalid tool; defaulting", tool=tool_name)
        tool_name = "query_metrics_db"
        args = {
            "metric": "reach",
            "aggregation": "sum",
            "limit": 10,
        }

    tool_result_text = await _execute_planned_tool(tool_name, args)

    synthesizer_system = (
        "You are a strict JSON formatter for analytics responses. "
        "Using the tool result, return ONLY valid JSON with keys: "
        "query_type, resolved_subject, result_data, insight_summary, verification. "
        "result_data must be an array of objects with fields: label, value, platform, content, title, published_at. "
        "Use empty strings when unknown and keep value as a string."
    )
    synth_user = (
        f"User question: {message}\n"
        f"Tool called: {tool_name}\n"
        f"Tool args: {json.dumps(args)}\n"
        f"Tool result: {tool_result_text}"
    )

    synth_resp = await provider.complete_with_retry(
        messages=[
            Message(role="system", content=synthesizer_system),
            Message(role="user", content=synth_user),
        ],
        temperature=0.1,
        max_tokens=900,
    )

    final_payload = _extract_json_object(synth_resp.content or "")
    return validate_provider_payload(
        final_payload,
        default_query_type=query_type,
        fallback_verification=f"tool={tool_name}; args={json.dumps(args)}; raw_result={tool_result_text[:1200]}",
    )
