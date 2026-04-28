"""Recommendation Agent — finds related articles for a given CMS article.

Uses CMS tools to fetch the source article and find semantically similar articles
via MongoDB vector search.

Pattern: Real Strands ``Agent`` with cms_tools registered.

Exported:
- ``RecommendationAgentSchema`` — response schema
- ``RecommendationAgent.execute`` — async entry point
- ``build_recommendation_agent`` — constructs a configured Strands ``Agent``
- ``get_agent``                  — factory helper
"""

from __future__ import annotations

import json
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

class ArticleRecommendation(PydanticBaseModel):
    """A single article recommendation."""
    id: str = Field(description="CMS article ID")
    title: str = Field(description="Article title")
    excerpt: str = Field(default="", description="Short excerpt or summary")
    published_at: str = Field(default="", description="Publication date/time")
    relevance_score: float = Field(description="Semantic similarity score (0-1)")
    relevance_label: str = Field(description="Human-readable relevance label")


class RecommendationAgentSchema(PydanticBaseModel):
    """Structured response from the recommendation agent."""
    response_text: str = Field(description="Human-readable response with article recommendations")
    source_article_id: str = Field(default="", description="The article ID used as the reference")
    recommendations: List[ArticleRecommendation] = Field(
        default_factory=list,
        description="Ranked list of recommended articles",
    )


RECOMMENDATION_SYSTEM_PROMPT = """\
You are an Article Recommendation Agent for a news content management system.

Your job:
1. Given an article ID, use fetch_article_by_id to retrieve the source article.
2. Use find_similar_articles with the article ID to discover semantically related articles.
3. Return a structured response with ranked recommendations and a brief explanation.

Guidelines:
- Parse the user message for an article ID (numeric or alphanumeric string).
- Parse for the requested number of recommendations (default 5 if not specified).
- Always include the article title, relevance score, and a brief description in response_text.
- If the source article cannot be found, explain clearly and return empty recommendations.
- Format response_text as a numbered list: "1. [Title] (relevance: X%) — [excerpt]"
"""


def build_recommendation_agent(model: Any) -> Agent:
    """Return a Strands Agent configured for article recommendations."""
    from app.tools.cms_tools import (  # local import
        fetch_article_by_id,
        find_similar_articles,
        format_article_recommendation,
    )

    return Agent(
        model=model,
        system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
        tools=[fetch_article_by_id, find_similar_articles, format_article_recommendation],
        callback_handler=None,
        structured_output_model=RecommendationAgentSchema,
    )


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class RecommendationAgent:
    """Finds related articles using semantic similarity."""

    def __init__(self) -> None:
        try:
            a = settings.main_agent
            self._agent_settings = a
        except Exception:
            from app.config import AISettings
            self._agent_settings = AISettings()
        self._factory = ProviderFactory(self._agent_settings)

    async def execute(self, context: Optional[Dict[str, Any]] = None) -> RecommendationAgentSchema:
        """Run the recommendation agent and return similar articles."""
        import asyncio

        if context is None:
            context = {}
        message: str = context.get("message") or ""

        model = self._factory.get_model(settings=self._agent_settings)
        agent = build_recommendation_agent(model)

        try:
            result = await asyncio.to_thread(agent, message)
            structured: Optional[RecommendationAgentSchema] = getattr(result, "structured_output", None)

            if structured is not None:
                return structured
            else:
                return RecommendationAgentSchema(response_text=str(result))

        except Exception as exc:
            logger.error("Recommendation agent error: %s", exc, exc_info=True)
            return RecommendationAgentSchema(
                response_text="I encountered an error while finding related articles. Please try again."
            )


def get_agent() -> RecommendationAgent:
    """Return a new RecommendationAgent instance."""
    return RecommendationAgent()
