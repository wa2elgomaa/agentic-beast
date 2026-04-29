"""Search Agent — searches thenationalnews.com using Google Custom Search Engine.

Uses Google CSE API to search for articles, topics, and authors in TNN.
Provides formatted search results with titles, links, and snippets.

Pattern: Real Strands ``Agent`` with search_tnn tool registered.

Exported:
- ``SearchAgentSchema``   — response schema
- ``SearchAgent.execute`` — async entry point
- ``build_search_agent``  — constructs a configured Strands ``Agent``
- ``get_agent``           — factory helper
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel as PydanticBaseModel, Field
from strands import Agent

from backend.src.app.config import settings
from backend.src.app.logging import get_logger
from backend.src.app.providers.factory import ProviderFactory

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class SearchResult(PydanticBaseModel):
    """A single search result from CSE."""
    title: str = Field(description="Article title")
    link: str = Field(description="Article URL")
    snippet: str = Field(description="Article excerpt/snippet")
    rank: int = Field(description="Result rank (1-based)")


class SearchAgentSchema(PydanticBaseModel):
    """Structured response from the search agent."""
    response_text: str = Field(
        description="Human-readable response with formatted search results"
    )
    query: str = Field(default="", description="The search query that was executed")
    results: List[SearchResult] = Field(
        default_factory=list,
        description="List of search results from CSE",
    )
    total_results: int = Field(default=0, description="Total number of results found")
    error: Optional[str] = Field(default=None, description="Error message if search failed")


SEARCH_SYSTEM_PROMPT = """\
You are a Search Agent for thenationalnews.com (Phase 2).

Your job:
1. Parse the user's search query from their message.
2. Use the search_tnn tool to query thenationalnews.com for relevant articles, topics, or authors.
3. Format the results as a numbered list with titles, snippets, and links.
4. If no results are found, acknowledge this gracefully.
5. If the search fails due to quota or API errors, explain the issue clearly.

Guidelines:
- Extract a concise search query from the user's message.
- Default to 5 results unless the user requests a different number.
- Format each result as: "[#] [Title] — [Snippet]... [Link]"
- Be helpful and suggest refinements if no results found.
- Support follow-up queries like "search for more" or "search for [new topic]".
- Track the query so the user knows what was searched.
"""


def build_search_agent(model: Any) -> Agent:
    """Return a Strands Agent configured for search."""
    from backend.src.app.tools.search_tools import search_tnn  # local import

    return Agent(
        model=model,
        system_prompt=SEARCH_SYSTEM_PROMPT,
        tools=[search_tnn],
        callback_handler=None,
        structured_output_model=SearchAgentSchema,
    )


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


class SearchAgent:
    """Searches thenationalnews.com for articles, topics, and authors."""

    def __init__(self) -> None:
        try:
            a = settings.search_agent
            if getattr(a, "provider", None) and getattr(a, "model_name", None):
                self._agent_settings = a
            else:
                self._agent_settings = settings.main_agent
        except Exception:
            self._agent_settings = settings.main_agent
        self._factory = ProviderFactory(self._agent_settings)

    async def execute(self, context: Optional[Dict[str, Any]] = None) -> SearchAgentSchema:
        """Run the search agent and return formatted search results.
        
        Args:
            context: Dictionary with 'message' key containing the user's search query
            
        Returns:
            SearchAgentSchema with formatted results or error message
        """
        import asyncio

        if context is None:
            context = {}
        message: str = context.get("message") or ""

        model = self._factory.get_model(settings=self._agent_settings)
        agent = build_search_agent(model)

        try:
            result = await asyncio.to_thread(agent, message)
            structured: Optional[SearchAgentSchema] = getattr(
                result, "structured_output", None
            )

            if structured is not None:
                return structured
            else:
                return SearchAgentSchema(response_text=str(result))

        except Exception as exc:
            logger.error("Search agent error: %s", exc, exc_info=True)
            return SearchAgentSchema(
                error=str(exc),
                response_text="I encountered an error while searching. Please try again later or refine your query.",
            )


def get_agent() -> SearchAgent:
    """Return a new SearchAgent instance."""
    return SearchAgent()
