"""classify_intent — Strands @tool and plain handler for the orchestrator.

Execution strategy (cheapest first):
  1. spaCy keyword/pattern matching  -- in-process, zero network cost
  2. Strands classify agent          -- only when spaCy returns 'unknown'
"""

from __future__ import annotations

from typing import Any

from strands import tool

from app.db.agent_session import build_agent_session_id
from app.utilities.intent_classifier import IntentClassifier, _VALID_INTENTS


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
        - "analytics"               -- any data/performance/insight query (top-N, reach,
                                       trends, compare, best posting time, publishing schedule)
        - "tag_suggestions"         -- user wants tag or label suggestions for content
        - "article_recommendations" -- user wants article / document recommendations
        - "unknown"                 -- none of the above
    """
    return await handle_intent(message)
