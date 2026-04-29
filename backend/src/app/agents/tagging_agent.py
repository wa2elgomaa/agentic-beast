"""Tagging Agent — suggests relevant tags for a CMS article.

Uses the CMS tools to fetch article content and the tag tools to find and rank
semantically similar tags from the tags table.

Pattern: Real Strands ``Agent`` with cms_tools + tag_tools registered.

Exported:
- ``TaggingAgentSchema``   — response schema
- ``TaggingAgent.execute`` — async entry point
- ``build_tagging_agent``  — constructs a configured Strands ``Agent``
- ``get_agent``            — factory helper
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel as PydanticBaseModel, Field
from strands import Agent

from app.config import settings
from app.logging import get_logger
from app.providers.factory import ProviderFactory

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class TagSuggestion(PydanticBaseModel):
    """A single tag suggestion with confidence score."""
    slug: str = Field(description="Tag slug identifier")
    name: str = Field(description="Human-readable tag name")
    rank: int = Field(description="Rank position (1 = most relevant)")
    combined_score: float = Field(description="Combined semantic + keyword relevance score (0-1)")
    relevance_label: str = Field(description="Human-readable relevance label")


class TaggingAgentSchema(PydanticBaseModel):
    """Structured response from the tagging agent."""
    response_text: str = Field(description="Human-readable response with tag suggestions")
    article_id: str = Field(default="", description="The article ID that was processed")
    tags: List[TagSuggestion] = Field(
        default_factory=list,
        description="Ranked list of suggested tags",
    )
    shown_tag_ids: List[str] = Field(
        default_factory=list,
        description="List of tag slugs shown in this response (for tracking 'show more' follow-ups — Phase 2)",
    )


TAGGING_SYSTEM_PROMPT = """\
You are a Tag Suggestion Agent for a news content management system (Phase 2).

Your job:
1. Given an article ID, use fetch_article_by_id to retrieve the article content.
2. Use find_similar_tags with the article's combined title + body to find candidate tags.
   - Prioritize efficiency: pass article_content (not article_embedding) to generate embedding once
3. Use rank_tags_by_relevance to produce a final ranked list of the top N tags.
4. Return a structured response with the ranked tag suggestions and a brief explanation.

Guidelines:
- Parse the user message for an article ID (numeric or alphanumeric string).
- Parse for the requested number of tags (default 5 if not specified).
- Always include the tag's name, rank, and score in your response_text.
- If the article cannot be found, explain clearly in response_text with an empty tags list.
- Format response_text as a numbered list: "1. [Tag Name] (relevance: X%) — [description]"

Support for follow-ups (user says "show me more tags"):
- If the conversation context includes 'previous_tags', pass them as exclude_ids to find_similar_tags
  so that previously shown tags are not repeated in subsequent calls.
"""


def build_tagging_agent(model: Any) -> Agent:
    """Return a Strands Agent configured for tag suggestion."""
    from app.tools.cms_tools import fetch_article_by_id  # local import
    from app.tools.tag_tools import find_similar_tags, rank_tags_by_relevance  # local import

    return Agent(
        model=model,
        system_prompt=TAGGING_SYSTEM_PROMPT,
        tools=[fetch_article_by_id, find_similar_tags, rank_tags_by_relevance],
        callback_handler=None,
        structured_output_model=TaggingAgentSchema,
    )


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class TaggingAgent:
    """Suggests relevant tags for a given CMS article."""

    def __init__(self) -> None:
        try:
            a = settings.tagging_agent
            if getattr(a, "provider", None) and getattr(a, "model_name", None):
                self._agent_settings = a
            else:
                self._agent_settings = settings.main_agent
        except Exception:
            self._agent_settings = settings.main_agent
        self._factory = ProviderFactory(self._agent_settings)

    async def execute(self, context: Optional[Dict[str, Any]] = None) -> TaggingAgentSchema:
        """Run the tagging agent and return tag suggestions.
        
        Supports follow-up requests for "more tags" by tracking shown_tag_ids
        and passing them as exclude_ids to find_similar_tags (Phase 2).
        """
        import asyncio

        if context is None:
            context = {}
        message: str = context.get("message") or ""

        model = self._factory.get_model(settings=self._agent_settings)
        agent = build_tagging_agent(model)

        try:
            result = await asyncio.to_thread(agent, message)
            structured: Optional[TaggingAgentSchema] = getattr(result, "structured_output", None)

            if structured is not None:
                # Populate shown_tag_ids for follow-up "more tags" requests
                structured.shown_tag_ids = [tag.slug for tag in structured.tags]
                return structured
            else:
                return TaggingAgentSchema(response_text=str(result))

        except Exception as exc:
            logger.error("Tagging agent error: %s", exc, exc_info=True)
            return TaggingAgentSchema(
                response_text="I encountered an error while suggesting tags. Please try again."
            )


def get_agent() -> TaggingAgent:
    """Return a new TaggingAgent instance."""
    return TaggingAgent()
