"""Provider-aware JSON chat helper.

This module centralizes JSON-only chat completion calls across providers so
intent parsing/classification and SQL generation can share identical behavior.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


async def generate_json_object(
    *,
    messages: list[dict[str, str]],
    model: str,
    timeout_seconds: float = 45.0,
    purpose: str = "json_chat",
) -> dict[str, Any]:
    """Generate a JSON object using the configured AI provider.

    Args:
        messages: Chat messages in provider-compatible role/content format.
        model: Model identifier to use.
        timeout_seconds: Request timeout.
        purpose: Logging label for observability.

    Returns:
        Parsed JSON object.

    Raises:
        RuntimeError: On transport/provider errors or non-JSON responses.
    """
    provider = (settings.ai_provider or "").strip().lower()

    if provider in {"openai", "strands"}:
        if not settings.effective_openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when AI_PROVIDER=openai")

        client_args: dict[str, Any] = {
            "api_key": settings.effective_openai_api_key,
            "base_url": settings.effective_openai_base_url,
        }

        client = AsyncOpenAI(**client_args)
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI JSON chat failed for {purpose}: {exc}") from exc

        raw = (resp.choices[0].message.content or "{}").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(
                "OpenAI JSON decode failed",
                purpose=purpose,
                model=model,
                raw_preview=raw[:200],
            )
            raise RuntimeError(f"OpenAI returned non-JSON for {purpose}") from exc

        if not isinstance(parsed, dict):
            raise RuntimeError(f"OpenAI returned non-object JSON for {purpose}")

        logger.info("JSON chat success", provider="openai", purpose=purpose, model=model)
        return parsed

    if provider == "ollama":
        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": model,
            "format": "json",
            "stream": False,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama HTTP {exc.response.status_code} for {purpose}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Ollama unreachable for {purpose}: {exc}") from exc

        raw = data.get("message", {}).get("content", "{}").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(
                "Ollama JSON decode failed",
                purpose=purpose,
                model=model,
                raw_preview=raw[:200],
            )
            raise RuntimeError(f"Ollama returned non-JSON for {purpose}") from exc

        if not isinstance(parsed, dict):
            raise RuntimeError(f"Ollama returned non-object JSON for {purpose}")

        logger.info("JSON chat success", provider="ollama", purpose=purpose, model=model)
        return parsed

    if provider == "litert_lm":
        # LiteRT_LM is available but not optimized for JSON mode API calls
        # Intent classification uses a separate code path with fallback to LLM
        # Other use cases (SQL generation, parsing, etc.) should use a traditional LLM
        raise RuntimeError(
            f"LiteRT_LM does not support JSON mode for {purpose}. "
            "For intent classification, it is automatically tried before LLM as a fallback. "
            "For other purposes, configure AI_PROVIDER to openai, strands, or ollama."
        )

    raise RuntimeError(
        f"Unsupported AI_PROVIDER '{settings.ai_provider}'. "
        "Expected one of: openai, strands, ollama, litert_lm"
    )
