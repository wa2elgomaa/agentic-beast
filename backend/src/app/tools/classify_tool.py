"""classify_intent -- @function_tool for the orchestrator.

Execution strategy (cheapest first):
  1. spaCy keyword/pattern matching  -- in-process, zero network cost
  2. gpt-4o-mini via Agent SDK       -- only when spaCy returns 'unknown'
"""
from typing import Any, cast

from agents import (
    ToolGuardrailFunctionOutput,
    ToolOutputGuardrail,
    function_tool,
    tool_output_guardrail,
)
from app.db.agent_session import build_agent_session_id
from app.utilities.intent_classifier import IntentClassifier, _VALID_INTENTS


def validate_intent(data: Any) -> ToolGuardrailFunctionOutput:
    text = str(data.output or "").strip().lower()
    print(f"classify intent tool output guardrail checking text: {text}")
    if text in {"unknown"}:
        return ToolGuardrailFunctionOutput.reject_content("Output intent was not actionable.")
    return ToolGuardrailFunctionOutput.allow()


validate_intent_guardrail = cast(
    ToolOutputGuardrail[Any],
    tool_output_guardrail(validate_intent),
)


async def handle_intent(message: str, context: dict[str, Any] | None = None) -> str:
    """Run only classification logic and return a validated intent."""
    session_id = build_agent_session_id("intent_classifier", context=context)
    intent = await IntentClassifier.simple(message)
    print(f"simple classify intent [{session_id}]: '{message}' -> '{intent}'")
    if intent == "unknown":
        intent = await IntentClassifier.complex(message, context=context)
        print(f"complex classify intent [{session_id}]: '{message}' -> '{intent}'")

    if intent not in _VALID_INTENTS:
        raise ValueError(f"Invalid intent classified: '{intent}'")

    return intent



@function_tool(
    tool_output_guardrails=[validate_intent_guardrail],
)
async def classify_intent_tool(message: str) -> str:
    """Classify the intent of a user message.

    Always tries fast in-process spaCy matching first.  Only falls back to
    gpt-4o-mini (via classify_agent) when spaCy cannot determine a clear intent.

    Args:
        message: The raw user message to classify.

    Returns:
        One of the following intent strings:
        - "query_metrics"  -- user wants numbers, counts, totals, views, reach
        - "analytics"      -- user wants insights, trends, or best/worst analysis
        - "ingestion"      -- user wants to import, upload, or process files
        - "tagging"        -- user wants content tags or category suggestions
        - "document_qa"    -- policy/procedure question or doc search
        - "unknown"        -- none of the above
    """
    return await handle_intent(message)

