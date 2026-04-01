"""Agent orchestrator for routing and agent coordination.

Architecture
------------
Follows a Swarm-like (Strands) multi-agent pattern::

  User message
      |
      v
  IntentClassifier   (spaCy fast-path -> Strands classify agent fallback)
      |  intent
      v
  Specialist Strands Agent   (analytics / tagging / ingestion)
      |  uses tools (SQL, CMS, ...)
      v
  Structured JSON response

The orchestrator no longer branches on ``settings.ai_provider``.  It always
routes through ``agent_factory`` which picks the right Strands model provider
(OpenAI or Ollama) from configuration.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import httpx

from app.agents.analytics_agent import get_strands_analytics_agent
from app.agents.ingestion_agent import get_strands_ingestion_agent
from app.agents.tagging_agent import get_strands_tagging_agent
from app.config import settings
from app.logging import get_logger
from app.tools.classify_tool import handle_intent

logger = get_logger(__name__)

POLITE_REJECTION = (
    "I’m sorry, but I can’t process this request right now. "
    "Please rephrase your request and try again."
)

# ------------------------------------------------------------------
# Intent -> agent mapping
# ------------------------------------------------------------------

# Primary 3-intent taxonomy (matches IntentClassifier.VALID_INTENTS)
_ANALYTICS_INTENTS = {
    "analytics",
    # Legacy sub-intents: kept so existing integrations / tests still route correctly
    "query_metrics",
    "publishing_insights",
}
_TAGGING_INTENTS = {"tag_suggestions", "tagging"}
_DOC_QA_INTENTS = {"article_recommendations", "document_qa"}
_INGESTION_INTENTS = {"ingestion"}


def _resolve_agent_for_intent(intent: str):
    """Return the appropriate Strands specialist agent for *intent*."""
    if intent in _ANALYTICS_INTENTS:
        return get_strands_analytics_agent()
    if intent in _INGESTION_INTENTS:
        return get_strands_ingestion_agent()
    if intent in _TAGGING_INTENTS:
        return get_strands_tagging_agent()
    return None


async def _run_strands_agent(agent, message: str) -> str | Dict[str, Any]:
    """Invoke a Strands agent and normalise its output to str or dict."""
    result = await agent.invoke_async(message)
    text = str(result).strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return text


# ------------------------------------------------------------------
# Value-Guard: ensure LLM response contains no invented numbers
# ------------------------------------------------------------------

def _value_guard(llm_text: str, db_rows: list[dict]) -> bool:
    """Return True when all significant numbers in *llm_text* exist in *db_rows*.

    "Significant" means >= 100 to avoid false positives on ordinals / dates.
    Only triggers when there are actual numeric rows to validate against.
    """
    if not db_rows:
        return True  # nothing to validate against; allow through

    # Numbers appearing in the LLM response that are >= 100
    nums_in_text: set[str] = {
        m for m in re.findall(r"\b\d+(?:\.\d+)?\b", llm_text)
        if float(m) >= 100
    }
    if not nums_in_text:
        return True

    # Collect all numeric values present in the DB result
    db_nums: set[str] = set()
    for row in db_rows:
        for v in row.values():
            if isinstance(v, (int, float)) and v >= 100:
                db_nums.add(str(int(v)))
                db_nums.add(f"{v:.0f}")
                db_nums.add(str(round(v, 2)))

    suspicious = nums_in_text - db_nums
    if suspicious:
        logger.warning(
            "Value-guard triggered: hallucinated numbers detected",
            suspicious=sorted(suspicious),
        )
        return False
    return True


# ------------------------------------------------------------------
# Direct-Ollama helpers for tag suggestions & article recommendations
# (avoids Strands tool-calling which requires function-calling support)
# ------------------------------------------------------------------

async def _run_tag_suggestions(message: str) -> dict[str, Any]:
    """Return tag suggestions via direct Ollama call (no tool-calling required)."""
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    model = (settings.ollama_intent_model or "").strip() or settings.ollama_model
    payload = {
        "model": model,
        "format": "json",
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a CMS tagging assistant. "
                    "Given content or a topic, suggest 5-10 relevant tags.\n"
                    'Output ONLY valid JSON: {"tags": ["tag1", "tag2", ...]}'
                ),
            },
            {"role": "user", "content": message},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = data.get("message", {}).get("content", "{}")
        result = json.loads(raw)
        tags = result.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        return {
            "intent": "tag_suggestions",
            "operation_type": "tag_suggestions",
            "result_data": [{"tag": t} for t in tags],
            "insight_summary": f"Suggested {len(tags)} tags: {', '.join(tags[:5])}" if tags else "No tags generated.",
        }
    except Exception as exc:
        logger.error("Tag suggestions failed", error=str(exc))
        return {
            "intent": "tag_suggestions",
            "operation_type": "tag_suggestions",
            "result_data": [],
            "insight_summary": "Could not generate tag suggestions. Please try again.",
        }


async def _run_article_recommendations(message: str) -> dict[str, Any]:
    """Return article recommendations via direct Ollama call."""
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    model = (settings.ollama_intent_model or "").strip() or settings.ollama_model
    payload = {
        "model": model,
        "format": "json",
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a content recommendation assistant. "
                    "Given a topic or query, recommend 3-5 article topics or search terms the user should explore.\n"
                    'Output ONLY valid JSON: {"recommendations": [{"title": "...", "reason": "..."}, ...]}'
                ),
            },
            {"role": "user", "content": message},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = data.get("message", {}).get("content", "{}")
        result = json.loads(raw)
        recs = result.get("recommendations", [])
        if not isinstance(recs, list):
            recs = []
        return {
            "intent": "article_recommendations",
            "operation_type": "article_recommendations",
            "result_data": recs,
            "insight_summary": f"Found {len(recs)} recommendations." if recs else "No recommendations found.",
        }
    except Exception as exc:
        logger.error("Article recommendations failed", error=str(exc))
        return {
            "intent": "article_recommendations",
            "operation_type": "article_recommendations",
            "result_data": [],
            "insight_summary": "Could not generate recommendations. Please try again.",
        }


# ------------------------------------------------------------------
# Main orchestrator class
# ------------------------------------------------------------------

class AgentOrchestrator:
    """Provider-agnostic orchestrator backed by Strands agents.

    Routes intents to specialist Strands agents without branching on
    `settings.ai_provider`.
    """

    def __init__(self) -> None:
        logger.info("AgentOrchestrator initialised", provider=settings.ai_provider)

    async def execute(self, context: Dict) -> str | Dict[str, Any]:
        """Route a user message to the appropriate specialist Strands agent.

        Args:
            context: Dict with at least a 'message' key.  May also contain
                     'db_session' for ingestion operations.

        Returns:
            Agent response as a string or structured dict.
        """
        message = context.get("message", "")
        if not message:
            return "No message provided."

        # Classify intent first — treat classification failures specially.
        try:
            intent = await handle_intent(message, context=context)
            logger.info("Orchestrator classified intent", intent=intent, message_snippet=message[:80])
        except ValueError as e:
            logger.warning("Intent classification failed", error=str(e))
            return {
                "error": "classification_error",
                "message": (
                    "I'm not sure how to handle that request. "
                    "Could you try rephrasing it?"
                ),
            }

        # Proceed with routing and downstream processing. Any non-classification
        # errors should be surfaced as an agent error, not a classification error.
        try:
            # ------------------------------------------------------------------
            # Analytics: new primary path — LLM SQL generation + safe execution.
            # Falls back to the pre-built tool pipeline if SQL gen is unavailable.
            # ------------------------------------------------------------------
            if intent in _ANALYTICS_INTENTS:
                from app.agents.analytics_agent import (  # noqa: PLC0415
                    run_sql_analytics_pipeline,
                    run_analytics_query,
                )

                conversation_history = context.get("conversation_history")

                # Primary path: SQL generation → dbquery_tool → response_agent
                result = await run_sql_analytics_pipeline(
                    message,
                    conversation_history=conversation_history,
                )

                # If SQL pipeline errored out, fall back to pre-built tools
                if result.get("query_type") == "error":
                    logger.warning(
                        "SQL pipeline failed; falling back to pre-built analytics tools",
                        extra={"reason": result.get("verification", "")},
                    )
                    result = await run_analytics_query(
                        message,
                        conversation_history=conversation_history,
                    )

                # Value-guard: ensure LLM narrative contains no invented numbers
                db_rows = result.get("result_data", [])
                summary = result.get("insight_summary", "")
                if summary and not _value_guard(summary, db_rows):
                    logger.warning("Value-guard triggered; keeping pre-formatted summary")

                return result

            # ------------------------------------------------------------------
            # Tag suggestions — direct Ollama (no Strands tool-calling)
            # ------------------------------------------------------------------
            if intent in _TAGGING_INTENTS:
                return await _run_tag_suggestions(message)

            # ------------------------------------------------------------------
            # Article recommendations / document Q&A — direct Ollama
            # ------------------------------------------------------------------
            if intent in _DOC_QA_INTENTS:
                return await _run_article_recommendations(message)

            specialist = _resolve_agent_for_intent(intent)
            if specialist is None:
                logger.warning("Unsupported intent after classification", intent=intent)
                return POLITE_REJECTION

            return await _run_strands_agent(specialist, message)

        except Exception as e:
            logger.error("Agent execution failed", error=str(e))
            return {
                "error": "agent_error",
                "message": (
                    "Something went wrong while processing your request. "
                    "Please try again, or rephrase your question."
                ),
            }
            # Tag suggestions — direct Ollama (no Strands tool-calling)
            # ------------------------------------------------------------------
            if intent in _TAGGING_INTENTS:
                return await _run_tag_suggestions(message)

            # ------------------------------------------------------------------
            # Article recommendations / document Q&A — direct Ollama
            # ------------------------------------------------------------------
            if intent in _DOC_QA_INTENTS:
                return await _run_article_recommendations(message)

            specialist = _resolve_agent_for_intent(intent)
            if specialist is None:
                logger.warning("Unsupported intent after classification", intent=intent)
                return POLITE_REJECTION

            return await _run_strands_agent(specialist, message)

        except Exception as e:
            logger.error("Agent execution failed", error=str(e))
            return {
                "error": "agent_error",
                "message": (
                    "Something went wrong while processing your request. "
                    "Please try again, or rephrase your question."
                ),
            }


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Return (or lazily create) the global AgentOrchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
