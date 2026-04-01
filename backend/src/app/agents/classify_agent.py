"""Intent-classify agent backed by Strands.

Exports:
  ``get_strands_classify_agent`` — factory returning a configured Strands Agent.
  ``_VALID_INTENTS``             — re-exported from ``intent_classifier`` for convenience.
"""

from __future__ import annotations

from typing import Optional

from app.utilities.intent_classifier import _VALID_INTENTS  # noqa: F401


def get_strands_classify_agent(selected_model: Optional[str] = None):
    """Return a Strands Agent for intent classification.

    Outputs exactly one intent label — no tools attached, reasons purely from
    the system prompt.

    Args:
        selected_model: Optional model override (e.g. ``"gpt-4o-mini"``).
                        Defaults to the model configured for the current AI_PROVIDER.
    """
    from strands import Agent  # noqa: PLC0415
    from app.agents.agent_factory import get_model_provider  # noqa: PLC0415

    model = get_model_provider(selected_model)

    system_prompt = (
        "You are an intent classifier. Respond with exactly one label and nothing else.\n"
        f"Allowed labels: {_VALID_INTENTS}.\n"
        "Intent definitions:\n"
        "- query_metrics: direct numeric asks (count, total, average, top-N by metric).\n"
        "- analytics: performance interpretation, trend diagnosis, winners/losers.\n"
        "- publishing_insights: best posting day/time/frequency recommendations.\n"
        "- ingestion: importing/uploading/processing datasets or checking job status.\n"
        "- tagging: generate/suggest/refine tags or categories for content.\n"
        "- document_qa: policy/process/knowledge-base questions from docs.\n"
        "- unknown: use only when no label above matches reliably.\n"
        "Tie-break rules:\n"
        "1) Specific numbers → prefer query_metrics over analytics.\n"
        "2) Posting schedule/timing strategy → prefer publishing_insights.\n"
        "3) Run/import/check a pipeline → prefer ingestion.\n"
        f"Return only one token from: {_VALID_INTENTS} or 'unknown'."
    )

    return Agent(
        name="IntentClassifier",
        model=model,
        system_prompt=system_prompt,
        callback_handler=None,
    )
        "You are an intent classifier. Respond with exactly one label and nothing else.\n"
        f"Allowed labels: {_VALID_INTENTS}.\n"
        "Intent definitions:\n"
        "- query_metrics: direct numeric asks (count, total, average, top-N by metric, comparisons by views/reach/impressions/interactions).\n"
        "- analytics: performance interpretation, trend diagnosis, root-cause analysis, winners/losers beyond raw counting.\n"
        "- publishing_insights: best posting day/time/frequency, scheduling windows, and publishing cadence recommendations.\n"
        "- ingestion: importing/uploading/processing datasets, starting ingestion jobs, or checking ingestion pipeline progress/status.\n"
        "- tagging: generate/suggest/refine tags, categories, or labels for content.\n"
        "- document_qa: policy/process/knowledge-base questions answered from docs or internal guidance.\n"
        "- unknown: use only when no label above is a reliable match.\n"
        "Tie-break rules:\n"
        "1) If the user asks for specific numbers, prefer query_metrics over analytics.\n"
        "2) If the request is about posting schedule/timing strategy, prefer publishing_insights.\n"
        "3) If the user asks to run/import/check a pipeline task, prefer ingestion.\n"
        f"Return only one token from: {_VALID_INTENTS} or 'unknown'."
    ),
)

