"""Strict schema validation for provider-synthesized response payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


def _sanitize_text(value: Any, max_len: int = 800) -> str:
    if value is None:
        return ""
    normalized = str(value).replace("\r", " ").replace("\n", " ")
    normalized = "".join(ch for ch in normalized if ch.isprintable() or ch.isspace())
    normalized = " ".join(normalized.split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len].rstrip()


class ProviderResultDataItem(BaseModel):
    """Result row expected by chat clients for synthesized provider payloads."""

    model_config = ConfigDict(extra="forbid")

    label: str = ""
    value: str = ""
    platform: str = ""
    content: str = ""
    title: str = ""
    published_at: str = ""

    @field_validator("label", "value", "platform", "content", "title", "published_at", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return _sanitize_text(value, max_len=600)


class ProviderSynthesisPayload(BaseModel):
    """Strict output schema for model-synthesized JSON responses."""

    model_config = ConfigDict(extra="forbid")

    query_type: str
    resolved_subject: str
    result_data: list[ProviderResultDataItem]
    insight_summary: str
    verification: str

    @field_validator("query_type", "resolved_subject", "insight_summary", "verification", mode="before")
    @classmethod
    def _normalize_top_level_text(cls, value: Any) -> str:
        return _sanitize_text(value, max_len=1200)


def validate_provider_payload(
    payload: dict[str, Any] | None,
    *,
    default_query_type: str,
    fallback_verification: str,
) -> dict[str, Any]:
    """Validate/normalize provider payload to strict schema.

    Returns a guaranteed schema-conforming dict. Invalid payloads are replaced
    with a safe fallback that preserves validation context in verification.
    """
    base_payload = payload or {}
    candidate = {
        "query_type": base_payload.get("query_type", default_query_type),
        "resolved_subject": base_payload.get("resolved_subject", default_query_type),
        "result_data": base_payload.get("result_data", []),
        "insight_summary": base_payload.get("insight_summary", ""),
        "verification": base_payload.get("verification", fallback_verification),
    }

    try:
        validated = ProviderSynthesisPayload.model_validate(candidate)
        return validated.model_dump(mode="json")
    except ValidationError as exc:
        fallback = ProviderSynthesisPayload(
            query_type=default_query_type,
            resolved_subject=default_query_type,
            result_data=[],
            insight_summary="Unable to validate provider response payload.",
            verification=f"{fallback_verification}; validation_error={_sanitize_text(exc, max_len=600)}",
        )
        return fallback.model_dump(mode="json")
