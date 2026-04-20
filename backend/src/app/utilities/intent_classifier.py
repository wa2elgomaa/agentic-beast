"""Intent classifier with dynamic taxonomy loaded from IntentRegistry.

Backward compatibility:
- Public API still returns legacy labels used by the orchestrator:
  analytics | tag_suggestions | article_recommendations | unknown
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.config import (
    get_intent_registry,
    get_agent_settings_registry,
    initialize_registries,
    settings,
)
from app.logging import get_logger
from app.utilities.json_chat import generate_json_object

logger = get_logger(__name__)

_LEGACY_INTENT_MAP = {
    "analytics": "analytics",
    "query_metrics": "analytics",
    "publishing_insights": "analytics",
    "trend_analysis": "analytics",
    "tagging": "tag_suggestions",
    "tag_suggestions": "tag_suggestions",
    "generate_tags": "tag_suggestions",
    "recommendation": "article_recommendations",
    "article_recommendations": "article_recommendations",
    "document_qa": "article_recommendations",
    "content_search": "article_recommendations",
    "general": "unknown",
    "unknown": "unknown",
}

_VALID_INTENTS = [
    "analytics",
    "tag_suggestions",
    "article_recommendations",
    "unknown",
]


def _ensure_registries_loaded() -> None:
    """Initialize registries lazily for CLI/test contexts.

    App startup already initializes these; this fallback avoids failures in
    direct script invocations.
    """
    try:
        get_intent_registry()
    except RuntimeError:
        initialize_registries(config_dir=settings.config_dir)


def _to_legacy_intent(intent_label: str) -> str:
    """Normalize canonical/alias labels to orchestrator-compatible labels."""
    normalized = (intent_label or "").strip().lower()
    if not normalized:
        return "unknown"
    return _LEGACY_INTENT_MAP.get(normalized, "unknown")


def _build_dynamic_prompt_parts() -> tuple[str, list[dict[str, str]]]:
    """Build system prompt and few-shot examples from IntentRegistry."""
    _ensure_registries_loaded()
    intent_registry = get_intent_registry()

    lines: list[str] = []
    few_shot: list[dict[str, str]] = []

    for intent_name in intent_registry.valid_intents:
        desc = intent_registry.get_intent_description(intent_name)
        aliases = intent_registry.get_intent_aliases(intent_name)
        legacy_label = _to_legacy_intent(intent_name)
        lines.append(f"- {legacy_label}: {desc} (canonical: {intent_name}; aliases: {aliases})")

        for example in intent_registry.get_intent_example_queries(intent_name)[:2]:
            few_shot.append({"role": "user", "content": example})
            few_shot.append({
                "role": "assistant",
                "content": (
                    '{"intent": "'
                    + legacy_label
                    + '", "confidence": 0.92, "reasoning": "matched intent definition"}'
                ),
            })

    system_prompt = (
        "You are a JSON-only intent classifier for an AI analytics platform.\n"
        "Return ONLY valid JSON with keys: intent, confidence, reasoning.\n"
        "No markdown, no extra text.\n\n"
        f"Allowed intent labels: {_VALID_INTENTS}\n"
        "Intent definitions loaded from runtime registry:\n"
        + "\n".join(lines)
        + "\n\n"
        "Rules:\n"
        "1) intent must be exactly one of the allowed labels\n"
        "2) confidence must be a float in [0,1]\n"
        "3) reasoning must be one short sentence\n"
        "4) If uncertain, use unknown\n"
        "5) If conversation context contains prior analytics SQL and the new user message is a follow-up/refinement, classify as analytics.\n"
    )
    return system_prompt, few_shot


def _context_snippet(context: dict[str, Any] | None) -> str:
    """Build compact context for intent classification prompt."""
    if not context:
        return "No context."

    history = context.get("conversation_history") or []
    if not isinstance(history, list) or not history:
        return "No conversation history."

    parts: list[str] = []
    for turn in history[-4:]:
        role = str(turn.get("role", "user"))
        content = str(turn.get("content", "")).replace("\n", " ")[:140]
        prior_sql = str(turn.get("prior_sql", ""))[:100]
        if role == "assistant" and prior_sql:
            parts.append(f"{role}: prior_sql={prior_sql}; text={content}")
        else:
            parts.append(f"{role}: {content}")
    return " | ".join(parts)


async def _classify_with_litert_lm(message: str, context: dict | None = None) -> dict[str, Any] | None:
    """Classify intent using LiteRT_LM local model.
    
    Args:
        message: User message to classify.
        context: Optional conversation context.
    
    Returns:
        Intent classification dict with keys: intent, confidence, reasoning, raw_intent, model
        Returns None if LiteRT_LM is disabled or model fails.
    """
    if not settings.litert_lm_enabled:
        return None
    
    try:
        try:
            import litert_lm  # noqa: F401
        except ImportError:
            logger.warning(
                "LiteRT_LM not installed; falling back to LLM classifier",
                error="litert_lm import failed",
            )
            return None

        from app.services.multimodal import get_polar_runtime_service

        runtime = get_polar_runtime_service()
        await runtime._ensure_runtime_loaded()
        if runtime._engine is None:
            return None

        system_prompt = (
            "You are a JSON-only intent classifier for an AI analytics platform. "
            "Return ONLY valid JSON with keys: intent, confidence, reasoning. "
            "Allowed intent values: analytics, tag_suggestions, article_recommendations, unknown."
        )
        user_prompt = (
            f"Conversation context: {_context_snippet(context)}\n"
            f"Current message: {message}"
        )

        loop = asyncio.get_running_loop()

        def _infer() -> str:
            conversation = runtime._engine.create_conversation(
                messages=[{"role": "system", "content": system_prompt}],
            )
            conversation.__enter__()
            try:
                response = conversation.send_message(
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": user_prompt}],
                    }
                )
                text = ""
                if isinstance(response, dict):
                    content = response.get("content")
                    if isinstance(content, list) and content:
                        first = content[0]
                        if isinstance(first, dict):
                            text = str(first.get("text", "")).strip()
                return text.strip()
            finally:
                conversation.__exit__(None, None, None)

        raw_text = await loop.run_in_executor(None, _infer)
        if not raw_text:
            return None

        payload = raw_text.strip()
        if payload.startswith("```"):
            payload = payload.strip("`").replace("json", "", 1).strip()

        parsed: dict[str, Any] | None = None
        try:
            loaded = json.loads(payload)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            start = payload.find("{")
            end = payload.rfind("}")
            if start >= 0 and end > start:
                try:
                    loaded = json.loads(payload[start : end + 1])
                    if isinstance(loaded, dict):
                        parsed = loaded
                except json.JSONDecodeError:
                    parsed = None

        if not parsed:
            return None

        raw_intent = str(parsed.get("intent", "")).strip().lower()
        normalized_intent = _to_legacy_intent(raw_intent)
        try:
            confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0

        min_threshold = float(settings.litert_lm_min_confidence_threshold)
        if normalized_intent not in _VALID_INTENTS or confidence < min_threshold:
            return None

        reasoning = str(parsed.get("reasoning", "")).strip() or "classified_with_litert_lm"
        return {
            "intent": normalized_intent,
            "confidence": confidence,
            "reasoning": reasoning,
            "raw_intent": raw_intent,
            "model": settings.litert_lm_intent_model,
        }

    except Exception as exc:
        logger.warning(
            "LiteRT_LM intent classification failed; falling back to LLM",
            error=str(exc),
        )
        return None


class IntentClassifier:
    """Dynamic intent classifier backed by registry-configured taxonomy."""

    VALID_INTENTS = _VALID_INTENTS

    @staticmethod
    async def classify_detailed(message: str, context: dict | None = None) -> dict[str, Any]:
        """Return structured intent classification with confidence and reasoning."""
        _ensure_registries_loaded()

        intent_registry = get_intent_registry()
        settings_registry = get_agent_settings_registry()

        fallback_intent = _to_legacy_intent(intent_registry.fallback_intent)
        if fallback_intent not in IntentClassifier.VALID_INTENTS:
            fallback_intent = "unknown"

        # Try LiteRT_LM classification first when enabled.
        if settings.litert_lm_enabled:
            litert_result = await _classify_with_litert_lm(message, context)
            if litert_result:
                logger.info(
                    "Intent classified with LiteRT_LM",
                    intent=litert_result.get("intent"),
                    confidence=litert_result.get("confidence"),
                    message_snippet=message[:80],
                )
                return litert_result
            if not settings.litert_lm_fallback_to_llm:
                return {
                    "intent": fallback_intent,
                    "confidence": 0.0,
                    "reasoning": "litert_classification_unavailable",
                    "raw_intent": "",
                    "model": settings.litert_lm_intent_model,
                }

        # Determine which LLM model to use
        if settings.ai_provider in ("openai", "strands"):
            intent_model = (settings.openai_intent_model or "").strip() or settings.openai_model
        elif settings.ai_provider == "litert_lm":
            intent_model = (
                (settings.openai_intent_model or "").strip()
                or settings.openai_model
                or (settings.ollama_intent_model or "").strip()
                or settings.ollama_model
            )
        else:
            intent_model = (settings.ollama_intent_model or "").strip() or settings.ollama_model

        system_prompt, few_shot = _build_dynamic_prompt_parts()
        timeout_seconds = settings_registry.get_agent_timeout("intent_classifier")

        messages = [
            {"role": "system", "content": system_prompt},
            *few_shot,
            {
                "role": "user",
                "content": (
                    f"Conversation context: {_context_snippet(context)}\n"
                    f"Current message: {message}"
                ),
            },
        ]

        try:
            parsed = await generate_json_object(
                messages=messages,
                model=intent_model,
                timeout_seconds=float(timeout_seconds),
                purpose="intent_classification",
            )
            raw_intent = str(parsed.get("intent", "")).strip().lower()
            normalized_intent = _to_legacy_intent(raw_intent)
            confidence_raw = parsed.get("confidence", 0.0)
            try:
                confidence = max(0.0, min(1.0, float(confidence_raw)))
            except (ValueError, TypeError):
                confidence = 0.0

            reasoning = str(parsed.get("reasoning", "")).strip() or "No reasoning returned by model"
            threshold = float(intent_registry.confidence_threshold)

            if normalized_intent not in IntentClassifier.VALID_INTENTS:
                logger.warning(
                    "Intent classifier returned invalid label; applying fallback",
                    raw_intent=raw_intent,
                    fallback=fallback_intent,
                    model=intent_model,
                )
                normalized_intent = fallback_intent
                confidence = 0.0

            if confidence < threshold:
                logger.info(
                    "Intent confidence below threshold; applying fallback",
                    raw_intent=raw_intent,
                    normalized_intent=normalized_intent,
                    confidence=confidence,
                    threshold=threshold,
                    fallback=fallback_intent,
                )
                normalized_intent = fallback_intent

            logger.info(
                "Intent classified",
                intent=normalized_intent,
                raw_intent=raw_intent,
                confidence=confidence,
                model=intent_model,
                message_snippet=message[:80],
            )

            return {
                "intent": normalized_intent,
                "confidence": confidence,
                "reasoning": reasoning,
                "raw_intent": raw_intent,
                "model": intent_model,
            }

        except Exception as exc:
            logger.error(
                "Intent classification failed; applying fallback",
                error=str(exc),
                fallback=fallback_intent,
                model=intent_model,
            )
            return {
                "intent": fallback_intent,
                "confidence": 0.0,
                "reasoning": "classification_error",
                "raw_intent": "",
                "model": intent_model,
            }

    @staticmethod
    async def complex(message: str, context: dict | None = None) -> str:
        """Compatibility method returning only the intent label string."""
        result = await IntentClassifier.classify_detailed(message, context=context)
        return result["intent"]

    @staticmethod
    async def classify(message: str, context: dict | None = None) -> str:
        """Public entry point used by orchestrator and tools."""
        intent = await IntentClassifier.complex(message, context=context)
        logger.debug("Final intent", intent=intent)
        return intent
