"""Provider-agnostic execution helpers for non-analytics intents."""

from __future__ import annotations

import json
from typing import Any

from app.agents.ingestion_agent import IngestionAgent
from app.logging import get_logger
from app.providers import get_ai_provider
from app.providers.base import Message
from app.services.provider_payload_validation import validate_provider_payload

logger = get_logger(__name__)


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


async def execute_ingestion_with_provider(message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute ingestion request without relying on OpenAI Agent SDK runtime."""
    db_session = (context or {}).get("db_session")
    if db_session is None:
        return validate_provider_payload(
            None,
            default_query_type="ingestion",
            fallback_verification="db_session_missing",
        )

    ingestion_agent = IngestionAgent(db_session)
    result_text = await ingestion_agent.execute(message)

    parsed = _extract_json_object(result_text)
    if parsed is not None:
        return validate_provider_payload(
            parsed,
            default_query_type="ingestion",
            fallback_verification="ingestion_agent_json",
        )

    payload = {
        "query_type": "ingestion",
        "resolved_subject": "ingestion",
        "result_data": [],
        "insight_summary": result_text,
        "verification": "ingestion_agent_text_response",
    }
    return validate_provider_payload(
        payload,
        default_query_type="ingestion",
        fallback_verification="ingestion_agent_text_fallback",
    )


async def execute_tagging_with_provider(message: str) -> dict[str, Any]:
    """Execute tagging intent using configured provider with strict schema output."""
    provider = get_ai_provider()

    system_prompt = (
        "You are a strict tagging assistant for newsroom content. "
        "Return ONLY valid JSON with keys: query_type, resolved_subject, result_data, insight_summary, verification. "
        "Set query_type='tagging'. "
        "result_data must be an array of objects with exactly these keys: "
        "label, value, platform, content, title, published_at. "
        "Use label for tag slug/name and value for confidence or rationale."
    )

    response = await provider.complete_with_retry(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=message),
        ],
        temperature=0.1,
        max_tokens=700,
    )

    payload = _extract_json_object(response.content or "")
    return validate_provider_payload(
        payload,
        default_query_type="tagging",
        fallback_verification="tagging_provider_validation",
    )
