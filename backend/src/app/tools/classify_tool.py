"""classify_intent — Strands @tool and plain handler for the orchestrator.

Execution strategy (cheapest first):
  1. spaCy keyword/pattern matching  -- in-process, zero network cost
  2. Strands classify agent          -- only when spaCy returns 'unknown'
"""

from __future__ import annotations

from typing import Any

from strands import tool

from app.db.agent_session import build_agent_session_id
from app.utils.intent_classifier import IntentClassifier, _VALID_INTENTS, _ensure_registries_loaded, _to_legacy_intent
from app.config import get_intent_registry


async def handle_intent(message: str, context: dict[str, Any] | None = None) -> str:
    """Run classification and return a validated intent string."""
    session_id = build_agent_session_id("intent_classifier", context=context)
    intent = await IntentClassifier.classify(message, context=context)
    print(f"classify intent [{session_id}]: '{message}' -> '{intent}'")

    if intent not in _VALID_INTENTS:
        raise ValueError(f"Invalid intent classified: '{intent}'")

    return intent


@tool
async def classify_intent_tool(message: str) -> str:
    """Classify the intent of a user message.

    Always tries fast in-process spaCy matching first.  Only falls back to
    the Strands classify agent when spaCy cannot determine a clear intent.

    Args:
        message: The raw user message to classify.

    Returns:
        One of the following intent strings:
        - "analytics"               -- any data/performance/insight query (top-N, reach, trends, compare, best posting time, publishing schedule)
        - "tag_suggestions"         -- user wants tag or label suggestions for content
        - "article_recommendations" -- user wants article / document recommendations
        - "general"                 -- user wants general information or assistance
        - "unknown"                 -- none of the above
    """
    return await handle_intent(message)


def _build_dynamic_prompt_parts() -> tuple[str, list[dict[str, str]]]:
    """Build system prompt and few-shot examples from IntentRegistry.

    This was formerly in `app.utilities.intent_classifier` — moved here so
    classification helpers live alongside the classify tool and agent.
    """
    try:
        _ensure_registries_loaded()
    except Exception:
        # If registries cannot be initialized, fall back to empty registry
        pass

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
                    '{"intent": "' + legacy_label + '", "confidence": 0.92, "reasoning": "matched intent definition"}'
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
