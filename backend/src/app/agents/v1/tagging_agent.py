"""Simple v1 TaggingAgent implementation.

This is a minimal, testable agent class used by the orchestrator and
`ChatService`. It is intentionally small to be extended later: it loads
agent-specific settings from the global `settings`, accepts a provider
factory for LLM requests, and exposes a `handle()` coroutine that
produces a response dict.
"""

from typing import Any, Dict, Optional
from strands import Agent
from app.config import settings
from app.logging import get_logger
from app.providers.factory import ProviderFactory
from pydantic import BaseModel as PydanticBaseModel, Field
from fastapi.encoders import jsonable_encoder
import asyncio
import json

logger = get_logger(__name__)


class TaggingAgentSchema(PydanticBaseModel):
    """Extract person information from text."""
    response_text: str = Field(description="Response from the tagging agent")
    response_json: Dict[str, Any] = Field(description="Structured JSON response from the tagging agent")

class TaggingAgent:
    """A callable agent that handles tagging requests.

    Usage:
        agent = TaggingAgent(provider_factory=ProviderFactory())
        # Backwards-compatible: accept (user_id, message, context)
        resp = await agent.handle(user_id, message, context={})
        # Or new orchestrator-friendly signature: pass a single `context` dict
        resp = await agent.handle({"message": "hi", "user_id": str(user_id)})
    """

    def __init__(self,):
        try:
            a = settings.tagging_agent
            if getattr(a, "provider", None) and getattr(a, "model_name", None):
                self.agent_settings = a
            else:
                self.agent_settings = settings.main_agent
        except Exception:
            self.agent_settings = settings.main_agent
        self.provider_factory = ProviderFactory(self.agent_settings)
        # Defer Agent construction to execute() to avoid import-time side effects.

    async def execute(self, context: Optional[Dict[str, Any]]) -> TaggingAgentSchema:
        """Handle a single user message and return a response dict.

        Compatible signatures:
        - load(user_id, message, context={})  # legacy
        - load(message, context={})           # message first
        - handle(context_dict)                  # orchestrator-friendly

        The implementation normalizes inputs then forwards the prompt to
        a provider resolved from the provider factory and returns the
        provider's response as `assistant_text`.
        """


        # const construct agent prompt from context
        if context is None:
            context = {}
        message = context.get("message") or ""
        
        model = self.provider_factory.get_model(settings=self.agent_settings)
        self.agent = Agent(model=model, tools=[])

        return self.agent.structured_output(
            output_model=TaggingAgentSchema,
            prompt=message,
        )

    def get_agent(self,):
        return self.agent
def get_agent() -> TaggingAgent:
    """Factory helper to instantiate a TaggingAgent with default ProviderFactory."""
    return TaggingAgent()
