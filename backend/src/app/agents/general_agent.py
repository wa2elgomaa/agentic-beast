"""General Assistant Agent — thin alias for the Chat Agent.

The general/fallback agent is identical to the chat agent: a no-tool
Strands Agent that answers any question the orchestrator could not route
to a more specialised sub-agent.

All symbols are re-exported from ``app.agents.v1.chat_agent`` so that
existing imports to this module continue to work without change.
"""

from app.agents.v1.chat_agent import (
    ChatAgent as GeneralAgent,
    ChatAgentSchema as GeneralAgentSchema,
    build_chat_agent as build_general_agent,
    get_agent,
)

__all__ = [
    "GeneralAgent",
    "GeneralAgentSchema",
    "build_general_agent",
    "get_agent",
]
