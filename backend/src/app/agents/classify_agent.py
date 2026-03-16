"""Defines classify_agent (gpt-4o-mini Agent) and re-exports IntentClassifier.

IntentClassifier logic lives in tools/intent_classifier.py to avoid circular
imports between tools/ and agents/.
"""

from agents import Agent
from app.utilities.intent_classifier import _VALID_INTENTS  # noqa: F401


classify_agent = Agent(
    name="IntentClassifier",
    model="gpt-4o-mini",
    instructions=(
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

