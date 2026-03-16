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


async def handle_intent(message: str) -> str:
    """Run only classification logic and return a validated intent."""
    intent = await IntentClassifier.simple(message)
    print(f"simple classify intent: '{message}' -> '{intent}'")
    if intent == "unknown":
        intent = await IntentClassifier.complex(message)
        print(f"complex classify intent: '{message}' -> '{intent}'")

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

