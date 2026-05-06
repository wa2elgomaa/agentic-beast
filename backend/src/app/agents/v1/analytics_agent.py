"""Analytics Agent — minimal, resilient implementation following the polar DataAnalyst pattern.

Flow (agent is the only brain):
  user message → agent
    → db_tool(sql)       — executes SELECT, injects rows/df into python_repl sandbox
    → python_repl(code)  — optional: transform data or create a matplotlib chart
    → text response

State: both tools share ``invocation_state["_sandbox"]`` (SDK-native, no closures).
Charts: model assigns matplotlib Figure to ``visualization`` in sandbox.
execute() reads it from result.state["_sandbox"] and encodes to base64 PNG.

Exported
--------
* ``AnalyticsAgentSchema``   — response schema
* ``build_analytics_agent``  — returns Agent (orchestrator calls .as_tool() on it)
* ``AnalyticsAgent``         — direct-call entry-point (used by ChatService)
* ``get_agent``              — factory helper
* ``_history_to_messages``   — used by orchestrator for follow-up seeding

Tools (in app.tools):
* ``app.tools.python_repl.python_repl``  — standalone @tool, uses invocation_state
* ``app.tools.dbquery_tool.db_tool``     — standalone @tool, uses invocation_state
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel as PydanticBaseModel, Field
from strands import Agent
from strands.agent import ModelRetryStrategy

from app.config import settings
from app.logging import get_logger
from app.providers.factory import ProviderFactory
from app.tools.dbquery_tool import db_tool
from app.tools.python_repl import python_repl
from app.utils.analytics_utils import build_schema_context

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Conversation history helpers
# ---------------------------------------------------------------------------

def _history_to_messages(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert conversation_history dicts to Strands message format."""
    messages: List[Dict[str, Any]] = []
    for turn in history:
        role = turn.get("role", "user")
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        messages.append({"role": role, "content": [{"text": content}]})
    return messages


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class AnalyticsAgentSchema(PydanticBaseModel):
    """Structured response returned by AnalyticsAgent."""
    response_text: str = Field(description="Human-readable analytics answer")
    response_json: str = Field(default="", description="JSON-serialised structured results")
    chart_b64: str = Field(default="", description="Base64-encoded PNG chart (empty if no chart)")
    visualization_caption: str = Field(default="", description="Caption for the chart")


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------

def build_analytics_agent(
    messages: Optional[List[Dict[str, Any]]] = None,
) -> Agent:
    """Return a Strands Agent with db_tool and python_repl.

    The orchestrator calls ``build_analytics_agent().as_tool(...)`` — so this
    always returns a plain Agent.

    Both tools communicate via SDK invocation_state["_sandbox"] — no closures or
    factory functions needed.

    Pass *messages* to seed prior conversation turns (follow-ups).
    """
    analytics_settings = settings.analytics_agent or settings.main_agent
    model = ProviderFactory(analytics_settings).get_model(settings=analytics_settings)

    #TODO: convert to prompt Template using jinja2 lib
    schema_context = build_schema_context()
    system_prompt = (
        f"{settings.analytics_system_prompt}\n\n"
        "=== Database Schema ===\n"
        f"{schema_context}\n"
    )

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[db_tool, python_repl],
        messages=cast(Any, messages or []),
        callback_handler=None,
        retry_strategy=ModelRetryStrategy(max_attempts=1),
    )


# ---------------------------------------------------------------------------
# AnalyticsAgent — direct-call entry point
# ---------------------------------------------------------------------------

class AnalyticsAgent:
    """Executes analytics queries directly (not via orchestrator sub-tool)."""

    def __init__(self) -> None:
        pass

    async def execute(self, context: Dict[str, Any]) -> AnalyticsAgentSchema:
        message: str = context.get("message") or ""
        history: List[Dict[str, Any]] = context.get("conversation_history") or []
        is_followup: bool = bool(context.get("is_followup", False))
        conversation_id: str = context.get("conversation_id") or ""

        initial_messages = _history_to_messages(history) if (is_followup and history) else []
        if initial_messages:
            logger.info("Analytics: follow-up — seeding with %d prior turns", len(initial_messages))
        else:
            logger.info("Analytics: fresh query")

        #TODO: limit the initial_messages to the most recent N turns or M tokens to avoid context bloat in long conversations.
        agent = build_analytics_agent(messages=initial_messages)

        response_text = ""
        chart_b64 = ""
        chart_caption = ""

        try:
            import asyncio as _asyncio

            def _run_sync() -> tuple:
                from app.tools.python_executor_tool import (
                    clear_chart_state,
                    pop_latest_chart,
                    set_conversation_id,
                )
                # Bind conversation_id into the ContextVar so that store_latest_chart
                # can write to the correct Redis key from any thread.
                if conversation_id:
                    set_conversation_id(conversation_id)
                clear_chart_state(conversation_id)
                result = agent(message)
                chart_b64, chart_caption = pop_latest_chart(conversation_id)
                return str(result), chart_b64, chart_caption

            response_text, chart_b64, chart_caption = await _asyncio.to_thread(_run_sync)
            if chart_b64:
                logger.info("Analytics: chart captured (%d base64 chars)", len(chart_b64))

        except Exception as exc:
            logger.error("Analytics agent error: %s", exc, exc_info=True)
            response_text = "An error occurred while processing your analytics query."

        return AnalyticsAgentSchema(
            response_text=response_text,
            chart_b64=chart_b64,
            visualization_caption=chart_caption,
        )


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def get_agent() -> AnalyticsAgent:
    """Return a new AnalyticsAgent instance."""
    return AnalyticsAgent()
