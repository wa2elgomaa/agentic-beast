from __future__ import annotations

from typing import Annotated, Optional

from strands import tool


@tool
def get_article_content(
    article_id: Annotated[str, "The article ID to look up."],
) -> str:
    """Fetch the content of an article."""
    return f"content for {article_id}"


@tool
def list_available_tags(
    article_id: Annotated[str, "The article ID to look up."],
) -> str:
    """List available tags for an article."""
    return f"available tags for {article_id}"


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def get_strands_tagging_agent(selected_model: Optional[str] = None):
    """Return a Strands Agent for CMS article tagging."""
    from strands import Agent  # noqa: PLC0415
    from app.agents.agent_factory import get_model_provider  # noqa: PLC0415

    model = get_model_provider(selected_model)
    return Agent(
        name="TaggingAgent",
        model=model,
        tools=[get_article_content, list_available_tags],
        system_prompt=(
            "You are a CMS tagging assistant. "
            "Use the available tools to fetch article content and suggest appropriate tags."
        ),
        callback_handler=None,
    )