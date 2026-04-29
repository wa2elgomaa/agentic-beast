"""Chat Agent — handles general conversation.

Pattern: Real Strands ``Agent`` with a configurable system prompt.
No tools needed — pure conversational LLM.

Exported
--------
* ``ChatAgentSchema``   — response schema
* ``ChatAgent.execute`` — async entry point
* ``build_chat_agent``  — constructs a configured Strands ``Agent``
* ``get_agent``         — factory helper
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel as PydanticBaseModel, Field
from strands import Agent

from app.config import settings
from app.logging import get_logger
from app.providers.factory import ProviderFactory

logger = get_logger(__name__)


class ChatAgentSchema(PydanticBaseModel):
    """Response schema for the chat agent."""
    response_text: str = Field(description="Conversational response to the user")


def build_chat_agent(model: Any) -> Agent:
    """Return a Strands Agent configured for general chat."""
    return Agent(
        model=model,
        system_prompt=settings.chat_system_prompt,
        tools=[],
        callback_handler=None,
    )


class ChatAgent:
    """Handles general chat queries through the Strands agent loop."""

    def __init__(self) -> None:
        try:
            a = settings.chat_agent
            if getattr(a, "provider", None) and getattr(a, "model_name", None):
                self._agent_settings = a
            else:
                self._agent_settings = settings.main_agent
        except Exception:
            self._agent_settings = settings.main_agent
        self._factory = ProviderFactory(self._agent_settings)

    async def execute(self, context: Optional[Dict[str, Any]] = None) -> ChatAgentSchema:
        """Handle a user message and return a conversational response."""
        if context is None:
            context = {}
        message: str = context.get("message") or ""

        model = self._factory.get_model(settings=self._agent_settings)
        agent = build_chat_agent(model)

        try:
            result = agent(message)
            response_text = str(result)
        except Exception as exc:
            logger.error("Chat agent error: %s", exc, exc_info=True)
            response_text = "I encountered an error. Please try again."

        return ChatAgentSchema(response_text=response_text)


def get_agent() -> ChatAgent:
    """Return a new ChatAgent instance."""
    return ChatAgent()

