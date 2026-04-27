"""ClassifyAgent — standalone intent classifier (kept for direct use / testing).

NOTE: The main orchestrator no longer calls this agent directly.
Routing is handled by the orchestrator LLM via the Agents-as-Tools pattern.
This class is retained for use in pipelines that require explicit intent labels.
"""

from typing import Any, Dict, List, Optional

from jinja2 import Template
from pydantic import BaseModel as PydanticBaseModel, Field
from strands import Agent

from app.config import settings
from app.logging import get_logger
from app.providers.factory import ProviderFactory

logger = get_logger(__name__)


class ClassifyAgentSchema(PydanticBaseModel):
    """Response schema: intent string (validated at runtime against allowed intents)."""
    intent: str = Field(description="One of the allowed intents")


DEFAULT_INTENTS: List[str] = ["analytics", "general", "unknown"]

SYSTEM_PROMPT_TPL = Template(
    "You are an intent classifier. Read the user's message and choose exactly ONE of the"
    " following intents: {% for i in intents %}`{{ i }}`{% if not loop.last %}, {% endif %}{% endfor %}."
    " Respond only with JSON matching the schema `{\"intent\": <one_of_values>}` and do not include any additional text."
)

class ClassifyAgent:
    """A callable agent that handles classification requests.

    Usage:
        agent = ClassifyAgent(provider_factory=ProviderFactory())
        # Backwards-compatible: accept (user_id, message, context)
        resp = await agent.handle(user_id, message, context={})
        # Or new orchestrator-friendly signature: pass a single `context` dict
        resp = await agent.handle({"message": "hi", "user_id": str(user_id)})
    """

    def __init__(self,):
        try:
            a = settings.classify_agent
            if getattr(a, "provider", None) and getattr(a, "model_name", None):
                self.agent_settings = a
            else:
                self.agent_settings = settings.main_agent
        except Exception:
            self.agent_settings = settings.main_agent
        self.provider_factory = ProviderFactory(self.agent_settings)
        # Do not construct Strands Agent at import time; create per-request in execute().
        # Determine allowed intents (configurable via settings)
        intents_cfg = None
        try:
            intents_cfg = getattr(settings, "classify_intents", None)
        except Exception:
            intents_cfg = None

        if not intents_cfg and getattr(self.agent_settings, "intents", None):
            intents_cfg = getattr(self.agent_settings, "intents")

        self.intents: List[str] = list(intents_cfg) if intents_cfg else DEFAULT_INTENTS
        self._prompt_template = SYSTEM_PROMPT_TPL

    async def execute(self, context: Optional[Dict[str, Any]]) -> ClassifyAgentSchema:
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

        prompt = self._prompt_template.render(intents=self.intents)
        prompt = f"{prompt}\n\nUser message:\n{message}"

        # Construct Strands Agent per-request to avoid import-time side effects.
        model = self.provider_factory.get_model(settings=self.agent_settings)
        self.agent = Agent(model=model, tools=[])

        result = self.agent.structured_output(
            output_model=ClassifyAgentSchema,
            prompt=prompt,
        )

        # Defensive validation: coerce to allowed intents or 'unknown'.
        intent_value = (getattr(result, "intent", "") or "").strip()
        if intent_value not in self.intents:
            fallback = "unknown" if "unknown" in self.intents else (self.intents[0] if self.intents else "unknown")
            intent_value = fallback

        return ClassifyAgentSchema(intent=intent_value)

    def get_agent(self,):
        return self.agent

def get_agent() -> ClassifyAgent:
    """Factory helper to instantiate a ClassifyAgent with default ProviderFactory."""
    return ClassifyAgent()
