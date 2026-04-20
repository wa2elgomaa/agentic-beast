"""Autonomous routing for analytics queries.

Replaces static follow-up regex heuristics with an LLM decision that considers:
- Current user message
- Conversation history (including prior SQL/metrics)
- Routing confidence threshold from config

Primary output target pipelines for analytics intent:
- "sql_analytics"
- "code_interpreter"
"""

from __future__ import annotations

import json
from typing import Any

from app.config import (
    get_agent_settings_registry,
    initialize_registries,
    settings,
)
from app.logging import get_logger
from app.utilities.json_chat import generate_json_object

logger = get_logger(__name__)

_VALID_TARGETS = {"sql_analytics", "code_interpreter"}


def _ensure_registries_loaded() -> None:
    try:
        get_agent_settings_registry()
    except RuntimeError:
        initialize_registries(config_dir=settings.config_dir)


def _conversation_summary(conversation_history: list[dict] | None) -> str:
    """Create a compact conversation summary for routing context."""
    if not conversation_history:
        return "No prior conversation context."

    entries: list[str] = []
    for idx, turn in enumerate(conversation_history[-6:], start=1):
        role = str(turn.get("role", "user"))
        content = str(turn.get("content", "")).replace("\n", " ")[:180]
        prior_sql = str(turn.get("prior_sql", ""))[:120]
        prior_metric = str(turn.get("prior_metric", ""))[:60]

        if role == "assistant" and prior_sql:
            entries.append(
                f"{idx}. assistant: sql={prior_sql}; metric={prior_metric}; text={content}"
            )
        else:
            entries.append(f"{idx}. {role}: {content}")

    return "\n".join(entries)


async def route_analytics_query(
    *,
    message: str,
    conversation_history: list[dict] | None,
) -> dict[str, Any]:
    """Route analytics queries to SQL pipeline vs code interpreter.

    Returns:
        {
          "target": "sql_analytics" | "code_interpreter",
          "confidence": float,
          "reasoning": str,
          "mode": "initial" | "follow_up" | "deep_analysis"
        }
    """
    _ensure_registries_loaded()

    settings_registry = get_agent_settings_registry()
    router_cfg = settings_registry.get_agent_config("router")
    follow_cfg = settings_registry.data.get("follow_up_detection", {})

    timeout_seconds = float(router_cfg.get("lm_timeout_seconds", 20.0))
    confidence_threshold = float(follow_cfg.get("confidence_threshold", 0.6))

    if settings.ai_provider in ("openai", "strands"):
        model = (settings.openai_intent_model or "").strip() or settings.openai_model
    elif settings.ai_provider == "litert_lm":
        # LiteRT_LM routing not yet supported; route to SQL by default
        logger.info("LiteRT_LM routing not yet optimized; defaulting to SQL analytics")
        return {
            "target": "sql_analytics",
            "confidence": 0.5,
            "reasoning": "LiteRT_LM routing unsupported; using default fallback",
            "mode": "initial",
        }
    else:
        model = (settings.ollama_intent_model or "").strip() or settings.ollama_model

    convo = _conversation_summary(conversation_history)

    system_prompt = (
        "You are an analytics routing agent. Decide whether to use SQL analytics "
        "or code interpreter for the next user query.\n"
        "Return ONLY valid JSON with keys: target, confidence, reasoning, mode.\n"
        "Allowed target values: sql_analytics, code_interpreter.\n"
        "Allowed mode values: initial, follow_up, deep_analysis.\n"
        "Routing guidance:\n"
        "- Choose sql_analytics for straightforward metric retrieval, top-N, single-step aggregates.\n"
        "- Choose code_interpreter for follow-ups, pronoun references, multi-step comparisons, "
        "transformations, or chart/plot requests.\n"
        "- If prior assistant turns include SQL and the user is refining previous results, prefer code_interpreter.\n"
        "- confidence must be between 0 and 1."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Conversation summary:\n{convo}\n\n"
                f"Current user message: {message}\n\n"
                "Choose the best target pipeline."
            ),
        },
    ]

    fallback = {
        "target": "sql_analytics",
        "confidence": 0.0,
        "reasoning": "router_fallback",
        "mode": "initial",
    }

    try:
        parsed = await generate_json_object(
            messages=messages,
            model=model,
            timeout_seconds=timeout_seconds,
            purpose="autonomous_router",
        )

        target = str(parsed.get("target", "")).strip().lower()
        reasoning = str(parsed.get("reasoning", "")).strip() or "no_reasoning"
        mode = str(parsed.get("mode", "initial")).strip().lower()
        confidence_raw = parsed.get("confidence", 0.0)

        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except (ValueError, TypeError):
            confidence = 0.0

        if target not in _VALID_TARGETS:
            logger.warning("Autonomous router returned invalid target", target=target)
            return fallback

        if mode not in {"initial", "follow_up", "deep_analysis"}:
            mode = "initial"

        if confidence < confidence_threshold:
            logger.info(
                "Autonomous router confidence below threshold; using SQL fallback",
                target=target,
                confidence=confidence,
                threshold=confidence_threshold,
            )
            return {
                "target": "sql_analytics",
                "confidence": confidence,
                "reasoning": f"low_confidence:{reasoning}",
                "mode": mode,
            }

        decision = {
            "target": target,
            "confidence": confidence,
            "reasoning": reasoning,
            "mode": mode,
        }
        logger.info("Autonomous router decision", **decision)
        return decision

    except Exception as exc:
        logger.error("Autonomous router failed; using fallback", error=str(exc))
        return fallback
