"""Analytics Agent — handles data analytics queries via a Strands agent loop.

Pattern: Real Strands ``Agent`` with ``sql_database_tool`` in its ``tools`` list.
The LLM drives the full pipeline autonomously:
  1. Generates SQL (using the schema context in the system prompt)
  2. Calls ``sql_database_tool`` to execute it against the DB
  3. Interprets the returned rows and produces a human-readable answer

This replaces the previous manual 3-step pipeline that bypassed the
Strands agent loop entirely.

Exported
--------
* ``AnalyticsAgentSchema``    — response schema consumed by orchestrator
* ``AnalyticsAgent.execute``  — async entry point
* ``build_analytics_agent``   — constructs a configured Strands ``Agent``
* ``get_agent``               — factory helper
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel as PydanticBaseModel, Field
from strands import Agent

from app.config import settings
from app.logging import get_logger
from app.providers.factory import ProviderFactory
from app.utils.analytics_utils import build_sql_gen_system_prompt

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Structured output schema — Strands forces the LLM to produce this shape
# ---------------------------------------------------------------------------

class AnalyticsOutputSchema(PydanticBaseModel):
    """Structured output produced by the analytics Strands agent.

    Strands passes this as ``structured_output_model`` so the LLM is
    constrained to return a validated Pydantic object — no tag-parsing needed.
    """

    response_text: str = Field(
        description=(
            "Human-readable analytics answer with key metrics highlighted. "
            "When listing videos or content items, render each as "
            "<a href='{view_on_platform}'>{content}</a> HTML anchor."
        )
    )
    results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Raw SQL result rows for the frontend result card. "
            "Copy every row returned by the sql_database tool query here as-is. "
            "For content/video rows ensure each dict contains: "
            "beast_uuid, content, title, view_on_platform, platform, published_date "
            "(and any metric columns)."
        ),
    )


# ---------------------------------------------------------------------------
# Legacy public schema — kept so ChatService import doesn't break
# ---------------------------------------------------------------------------

class AnalyticsAgentSchema(PydanticBaseModel):
    """Structured response returned by AnalyticsAgent."""
    response_text: str = Field(description="Human-readable analytics answer")
    response_json: str = Field(
        default="", description="JSON-serialised structured results"
    )


# ---------------------------------------------------------------------------
# Agent builder (pure function — usable as sub-agent tool)
# ---------------------------------------------------------------------------

def build_analytics_agent(model: Any) -> Agent:
    """Return a Strands Agent wired with sql_database_tool.

    The agent uses ``structured_output_model=AnalyticsOutputSchema`` so every
    invocation (direct *and* via .as_tool() inside the orchestrator) returns
    a validated Pydantic object — no regex/tag parsing needed.
    """
    from app.tools.dbquery_tool import sql_database_tool  # local to avoid circular imports

    schema_context = build_sql_gen_system_prompt()

    system_prompt = (
        f"{settings.analytics_system_prompt}\n\n"
        "=== Database Schema Context ===\n"
        f"{schema_context}"
    )

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[sql_database_tool],
        callback_handler=None,
        structured_output_model=AnalyticsOutputSchema,
    )


# ---------------------------------------------------------------------------
# Agent class (used when analytics_agent is invoked directly, not as sub-tool)
# ---------------------------------------------------------------------------

class AnalyticsAgent:
    """Executes analytics queries through the Strands agent loop."""

    def __init__(self) -> None:
        try:
            a = settings.analytics_agent
            if getattr(a, "provider", None) and getattr(a, "model_name", None):
                self._agent_settings = a
            else:
                self._agent_settings = settings.main_agent
        except Exception:
            self._agent_settings = settings.main_agent
        self._factory = ProviderFactory(self._agent_settings)

    async def execute(self, context: Dict[str, Any]) -> AnalyticsAgentSchema:
        """Run the analytics agent and return a structured response."""
        message: str = context.get("message") or ""
        model = self._factory.get_model(settings=self._agent_settings)
        agent = build_analytics_agent(model)

        try:
            result = agent(message)
            structured: Optional[AnalyticsOutputSchema] = getattr(result, "structured_output", None)

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
            logger.error("Analytics agent error: %s", exc, exc_info=True)
            response_text = "An error occurred while processing your analytics query."
            response_json = ""

        return AnalyticsAgentSchema(
            response_text=response_text,
            response_json=response_json,
        )


# (JSON extraction is handled natively via AnalyticsOutputSchema structured_output_model)


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def get_agent() -> AnalyticsAgent:
    """Return a new AnalyticsAgent instance."""
    return AnalyticsAgent()
