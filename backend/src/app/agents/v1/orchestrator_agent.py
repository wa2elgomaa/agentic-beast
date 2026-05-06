"""Orchestrator Agent — routes user requests to specialist sub-agents.

Pattern: Agents as Tools (Strands SDK).
The orchestrator is a real Strands ``Agent`` whose ``tools`` list contains
the analytics and chat sub-agents wrapped via ``.as_tool()``.  The LLM
decides which specialist to call based on the ``system_prompt`` — no manual
``if intent ==`` routing.

Entry points
------------
* ``OrchestratorAgent.execute(context)``  — async, used by ``ChatService``
* ``get_agent() / get_orchestrator()``    — factory helpers
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from pydantic import BaseModel as PydanticBaseModel, Field
from strands import Agent
from strands.agent import ModelRetryStrategy

from app.config import settings
from app.logging import get_logger
from app.providers.factory import ProviderFactory

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Structured output schema — forces the orchestrator LLM to relay results
# ---------------------------------------------------------------------------

class OrchestratorOutputSchema(PydanticBaseModel):
    """Structured output produced by the orchestrator Strands agent.

    When the analytics_agent sub-tool is called, ``results`` will be populated
    from the sub-agent's ``AnalyticsOutputSchema.results`` that Strands relays
    as part of the tool result.  For chat-only queries ``results`` is empty.
    """

    response_text: str = Field(
        description=(
            "Complete human-readable response to the user. "
            "Relay the analytics answer verbatim (including any HTML anchor tags)."
        )
    )


# ---------------------------------------------------------------------------
# Legacy public schema — kept so ChatService import doesn't break
# ---------------------------------------------------------------------------

class OrchestratorAgentSchema(PydanticBaseModel):
    """Unified response returned to ChatService / API layer."""
    response_text: str = Field(description="Human-readable response to the user")
    chart_b64: str = Field(default="", description="Base64-encoded PNG chart (empty if no chart)")
    visualization_caption: str = Field(default="", description="Caption for the chart")


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class OrchestratorAgent:
    """Routes every chat request through a Strands Agent + sub-agent tools."""

    def __init__(self) -> None:
        self._settings = settings.main_agent
        self._factory = ProviderFactory(self._settings)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_history_for_prompt(
        history: List[Dict[str, Any]],
        current_message: str,
    ) -> str:
        """Augment the current message with conversation history so the LLM has context.

        Each assistant turn also injects ``prior_sql`` and ``prior_rows`` when
        present, allowing analytics follow-ups like "sum the results" to work
        without hitting the database again.
        """
        if not history:
            return current_message

        parts: List[str] = ["[CONVERSATION HISTORY]"]
        for turn in history:
            role = turn.get("role", "user")
            content = str(turn.get("content", "")).strip()
            prefix = "User" if role == "user" else "Assistant"
            parts.append(f"{prefix}: {content}")
            if role == "assistant":
                if prior_sql := turn.get("prior_sql"):
                    parts.append(f"[Prior SQL]: {prior_sql}")
                if prior_rows := turn.get("prior_rows"):
                    rows_preview = json.dumps(prior_rows[:5], default=str)
                    parts.append(
                        f"[Prior Data ({len(prior_rows)} rows, showing first 5)]: {rows_preview}"
                    )
        parts.append("[END CONVERSATION HISTORY]")
        parts.append(f"\nUser (current): {current_message}")
        return "\n".join(parts)

    def _build_agent(
        self,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Agent:
        """Construct a fresh Strands Agent per request.

        Returns a tuple of (orchestrator_agent, analytics_agent). Callers keep
        a reference to analytics_agent so they can read its invocation_state
        sandbox to retrieve chart data after the agent run completes.
        """
        from app.agents.v1.analytics_agent import build_analytics_agent
        from app.agents.v1.chat_agent import build_chat_agent

        orchestrator_model = self._factory.get_model(settings=self._settings)

        analytics_agent = build_analytics_agent(
            messages=initial_messages or []
        )

        analytics_tool = analytics_agent.as_tool(
            name="analytics_agent",
            description=(
                "Use for any data, metrics, statistics, rankings, trends, or performance "
                "queries about social media content or platform analytics. "
                "Pass the user's exact question as input."
            ),
        )
        chat_tool = build_chat_agent().as_tool(
            name="chat_agent",
            description=(
                "Use for general conversation, questions, explanations, summaries, "
                "or anything not related to data analytics. "
                "Pass the user's exact message as input."
            ),
        )

        return Agent(
            model=orchestrator_model,
            system_prompt=settings.orchestrator_system_prompt,
            tools=[analytics_tool, chat_tool],
            # Suppress default stdout printing — responses come via AgentResult.
            callback_handler=None,
            # No retries — prevents extra API calls on transient errors.
            retry_strategy=ModelRetryStrategy(max_attempts=1),
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def execute(self, context: Optional[Dict[str, Any]] = None) -> OrchestratorAgentSchema:
        """Route a user request through the orchestrator and return a structured response."""
        from app.agents.v1.analytics_agent import _history_to_messages
        from app.agents.v1.classify_agent import ClassifyAgent

        if context is None:
            context = {}
        message: str = context.get("message") or ""
        history: List[Dict[str, Any]] = context.get("conversation_history") or []
        augmented_message = self._format_history_for_prompt(history, message)

        # Classify intent + follow-up before building agent so we can seed
        # the analytics sub-agent with the right history up front.
        initial_messages: List[Dict[str, Any]] = []
        try:
            classify_result = await ClassifyAgent().execute(context)
            context["is_followup"] = classify_result.followup
            if classify_result.followup and history:
                initial_messages = _history_to_messages(history)
                logger.info(
                    "Orchestrator: follow-up detected — seeding analytics with %d prior turns",
                    len(initial_messages),
                )
        except Exception as exc:
            logger.warning("ClassifyAgent failed in orchestrator: %s", exc)

        # _build_agent() returns (orchestrator_agent, analytics_agent)
        agent = self._build_agent(initial_messages=initial_messages)

        conversation_id: str = context.get("conversation_id") or ""

        try:
            from app.tools.python_executor_tool import (
                clear_chart_state,
                pop_latest_chart,
                set_conversation_id,
            )
            if conversation_id:
                set_conversation_id(conversation_id)
            clear_chart_state(conversation_id)
            result = agent(augmented_message)
            response_text = str(result)
            chart_b64, chart_caption = pop_latest_chart(conversation_id)

        except Exception as exc:
            logger.error("Orchestrator agent error: %s", exc, exc_info=True)
            response_text = "I encountered an error processing your request. Please try again."
            chart_b64 = ""
            chart_caption = ""
  

        return OrchestratorAgentSchema(
            response_text=response_text,
            chart_b64=chart_b64,
            visualization_caption=chart_caption,
        )

    async def execute_stream(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream the orchestrator response as a series of typed events.

        Yields dicts with ``type`` keys:
        - ``{"type": "thinking"}`` — immediately, before any processing
        - ``{"type": "text_chunk", "data": {"text": "...", "index": N}}`` — word chunks
        - ``{"type": "complete", "data": {...}}`` — final structured payload
        - ``{"type": "error", "message": "..."}`` — on failure
        """
        import asyncio

        if context is None:
            context = {}
        message: str = context.get("message") or ""
        history: List[Dict[str, Any]] = context.get("conversation_history") or []
        augmented_message = self._format_history_for_prompt(history, message)

        yield {"type": "thinking"}

        # Classify intent + follow-up before building agent.
        from app.agents.v1.analytics_agent import _history_to_messages
        from app.agents.v1.classify_agent import ClassifyAgent

        initial_messages: List[Dict[str, Any]] = []
        try:
            classify_result = await ClassifyAgent().execute(context)
            context["is_followup"] = classify_result.followup
            if classify_result.followup and history:
                initial_messages = _history_to_messages(history)
                logger.info(
                    "Orchestrator stream: follow-up detected — seeding analytics with %d prior turns",
                    len(initial_messages),
                )
        except Exception as exc:
            logger.warning("ClassifyAgent failed in orchestrator stream: %s", exc)

        # _build_agent() calls clear_chart_state() internally before wiring tools
        agent = self._build_agent(initial_messages=initial_messages)

        conversation_id: str = context.get("conversation_id") or ""

        try:

            def _run_agent():
                """Execute the agent synchronously; return (response_text, chart_b64, chart_caption)."""
                from app.tools.python_executor_tool import (
                    clear_chart_state,
                    pop_latest_chart,
                    set_conversation_id,
                )
                if conversation_id:
                    set_conversation_id(conversation_id)
                clear_chart_state(conversation_id)
                result = agent(augmented_message)
                chart_b64, chart_caption = pop_latest_chart(conversation_id)
                return str(result), chart_b64, chart_caption

            # Run the agent in a background thread to avoid blocking the event loop.
            result_tuple = await asyncio.to_thread(_run_agent)
            response_text, chart_b64, chart_caption = result_tuple

            # Stream response_text word by word for a live-typing UX.
            words = response_text.split(" ")
            for i, word in enumerate(words):
                chunk = word if i == 0 else f" {word}"
                yield {"type": "text_chunk", "data": {"text": chunk, "index": i}}
                await asyncio.sleep(0)  # yield to the event loop between chunks

            # Emit image event before complete if a chart was generated
            if chart_b64:
                yield {
                    "type": "image",
                    "data": {
                        "b64": chart_b64,
                        "mime": "image/png",
                        "caption": chart_caption,
                    },
                }

            yield {
                "type": "complete",
                "data": {
                    "response_text": response_text,
                    "chart_b64": chart_b64,
                    "visualization_caption": chart_caption,
                },
            }

        except Exception as exc:
            logger.error("Orchestrator stream error: %s", exc, exc_info=True)
            yield {"type": "error", "message": "I encountered an error processing your request. Please try again."}


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def get_agent() -> OrchestratorAgent:
    """Return a new OrchestratorAgent instance."""
    return OrchestratorAgent()


# Alias used by ChatService
get_orchestrator = get_agent
