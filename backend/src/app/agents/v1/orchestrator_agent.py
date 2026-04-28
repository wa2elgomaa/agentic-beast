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
    results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "If analytics_agent was called, copy the result rows from its structured "
            "output here exactly as-is. For chat or non-data queries leave empty."
        ),
    )


# ---------------------------------------------------------------------------
# Legacy public schema — kept so ChatService import doesn't break
# ---------------------------------------------------------------------------

class OrchestratorAgentSchema(PydanticBaseModel):
    """Unified response returned to ChatService / API layer."""
    response_text: str = Field(description="Human-readable response to the user")
    response_json: str = Field(
        default="", description="JSON-serialised structured payload (analytics results, etc.)"
    )


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
                prior_sql = turn.get("prior_sql")
                if prior_sql:
                    parts.append(f"[Prior SQL]: {prior_sql}")
                prior_rows = turn.get("prior_rows")
                if prior_rows:
                    rows_preview = json.dumps(prior_rows[:5], default=str)
                    parts.append(
                        f"[Prior Data ({len(prior_rows)} rows, showing first 5)]: {rows_preview}"
                    )
        parts.append("[END CONVERSATION HISTORY]")
        parts.append(f"\nUser (current): {current_message}")
        return "\n".join(parts)

    def _build_agent(self) -> Agent:
        """Construct a fresh Strands Agent per request.

        A fresh agent guarantees clean conversation state for each request.
        Sub-agents are wired in via ``.as_tool()`` so the orchestrator LLM
        can call them as standard tool invocations.
        """
        from app.agents.v1.analytics_agent import build_analytics_agent
        from app.agents.v1.chat_agent import build_chat_agent
        from app.agents.tagging_agent import build_tagging_agent
        from app.agents.recommendation_agent import build_recommendation_agent
        from app.agents.document_agent import build_document_agent

        model = self._factory.get_model(settings=self._settings)

        analytics_tool = build_analytics_agent(model).as_tool(
            name="analytics_agent",
            description=(
                "Use for any data, metrics, statistics, rankings, trends, or performance "
                "queries about social media content or platform analytics. "
                "Pass the user's exact question as input."
            ),
        )
        chat_tool = build_chat_agent(model).as_tool(
            name="chat_agent",
            description=(
                "Use for general conversation, questions, explanations, summaries, "
                "general knowledge, trivia, math, coding help, or anything not related "
                "to data analytics, tag suggestions, article recommendations, or company documents. "
                "This is also the fallback when no other agent matches. "
                "Pass the user's exact message as input."
            ),
        )
        tagging_tool = build_tagging_agent(model).as_tool(
            name="tagging_agent",
            description=(
                "Use when the user asks for tag suggestions, content tagging, or wants to find "
                "relevant tags for an article. Examples: 'suggest tags for article 123', "
                "'what tags fit this article', 'tag article ID 456 with 5 tags'. "
                "Pass the user's exact message as input."
            ),
        )
        recommendation_tool = build_recommendation_agent(model).as_tool(
            name="recommendation_agent",
            description=(
                "Use when the user asks for similar, related, or recommended articles. "
                "Examples: 'find similar articles to 123', 'suggest 3 related stories for article 456', "
                "'what articles are like article 789'. "
                "Pass the user's exact message as input."
            ),
        )
        document_tool = build_document_agent(model).as_tool(
            name="document_agent",
            description=(
                "Use when the user asks questions about internal company documents, policies, "
                "procedures, or uploaded files. Examples: 'what does the onboarding document say', "
                "'find information about our vacation policy', 'search company documents for X'. "
                "Pass the user's exact question as input."
            ),
        )
        return Agent(
            model=model,
            system_prompt=settings.orchestrator_system_prompt,
            tools=[
                analytics_tool,
                chat_tool,
                tagging_tool,
                recommendation_tool,
                document_tool,
            ],
            # Suppress default stdout printing — responses come via AgentResult.
            callback_handler=None,
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def execute(self, context: Optional[Dict[str, Any]] = None) -> OrchestratorAgentSchema:
        """Route a user request through the orchestrator and return a structured response."""
        if context is None:
            context = {}
        message: str = context.get("message") or ""
        history: List[Dict[str, Any]] = context.get("conversation_history") or []
        augmented_message = self._format_history_for_prompt(history, message)

        agent = self._build_agent()

        try:
            # Structured output forces the LLM to produce OrchestratorOutputSchema
            # with response_text (human answer) + results (relay from analytics sub-tool).
            result = agent(augmented_message, structured_output_model=OrchestratorOutputSchema)
            structured: Optional[OrchestratorOutputSchema] = getattr(result, "structured_output", None)

            if structured is not None:
                response_text = structured.response_text
                response_json = (
                    json.dumps({"results": structured.results}, default=str)
                    if structured.results
                    else ""
                )
            else:
                # Fallback: structured output unavailable (model/provider doesn't support it)
                response_text = str(result)
                response_json = ""

        except Exception as exc:
            logger.error("Orchestrator agent error: %s", exc, exc_info=True)
            response_text = "I encountered an error processing your request. Please try again."
            response_json = ""

        return OrchestratorAgentSchema(
            response_text=response_text,
            response_json=response_json,
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

        agent = self._build_agent()

        try:
            # Run the synchronous Strands agent in a thread so we don't block
            # the event loop while the LLM completes.
            result = await asyncio.to_thread(
                agent, augmented_message, structured_output_model=OrchestratorOutputSchema
            )
            structured: Optional[OrchestratorOutputSchema] = getattr(result, "structured_output", None)

            if structured is not None:
                response_text = structured.response_text
                results = structured.results
            else:
                response_text = str(result)
                results = []

            # Stream response_text word by word for a live-typing UX.
            words = response_text.split(" ")
            for i, word in enumerate(words):
                chunk = word if i == 0 else f" {word}"
                yield {"type": "text_chunk", "data": {"text": chunk, "index": i}}
                await asyncio.sleep(0)  # yield to the event loop between chunks

            yield {
                "type": "complete",
                "data": {
                    "response_text": response_text,
                    "results": results,
                    "response_json": json.dumps({"results": results}, default=str) if results else "",
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
