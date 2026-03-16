from typing import Annotated

from agents import Agent, ToolSearchTool, function_tool, tool_namespace


@function_tool(defer_loading=True)
def get_article_content(
    article_id: Annotated[str, "The article ID to look up."],
) -> str:
    """Fetch the content of an article."""
    return f"content for {article_id}"


@function_tool(defer_loading=True)
def list_available_tags(
    article_id: Annotated[str, "The article ID to look up."],
) -> str:
    """List available tags for an article."""
    return f"available tags for {article_id}"


cms_tools = tool_namespace(
    name="cms",
    description="CMS tools for article content and tagging.",
    tools=[get_article_content, list_available_tags],
)

tagging_agent = Agent(
    name="Tagging assistant",
    model="gpt-5.4",
    instructions="Load article content and tagging tools before using the agent.",
    tools=[*cms_tools, ToolSearchTool()],
)