"""Agent orchestrator for routing and agent coordination."""

from typing import Any, Dict, Optional
import json
from app.config import settings
from agents import Agent, Runner, set_default_openai_key
from app.logging import get_logger
from app.tools.classify_tool import handle_intent, classify_intent_tool
from app.agents.analytics_agent import analytics_agent as analytics_openai_agent
from app.db.agent_session import get_agent_sqlalchemy_session
from app.agents.ingestion_agent import ingestion_openai_agent

logger = get_logger(__name__)

POLITE_REJECTION = (
    "I’m sorry, but I can’t process this request right now. "
    "Please rephrase your request and try again."
)

# SDK-level orchestrator agent: calls classify_intent tool and can handoff
# to the OpenAI-built analytics or ingestion agents.
openai_orchestrator = Agent(
    name="OpenAI Orchestrator",
    model="gpt-4o",
    instructions="""
    Orchestrator: always call the `classify_intent_tool` with the user's message,
    then choose the appropriate handoff based on the returned intent.
    """,
    tools=[classify_intent_tool],
    handoffs=[analytics_openai_agent, ingestion_openai_agent],
)

class AgentOrchestrator:
    """Orchestrator for managing multiple agents and routing intents."""

    def __init__(self):
        """Initialize the orchestrator."""
        set_default_openai_key(settings.openai_api_key)

    async def execute(self, context: Dict) -> str | Dict[str, Any]:
        """Execute routing for a given context.

        The context may include either an explicit `intent` or a `message`.
        If only `message` is present, use the `IntentClassifier` to determine
        the intent before routing.
        """
 
        # Otherwise, delegate to the SDK-level orchestrator so the model
        # can call the `classify_intent` tool and perform autonomous handoffs.
        message = context.get("message", "")
        if not message:
            return "No message provided."

        try:
            # Run classification first and wait for its result before routing.
            intent = await handle_intent(message, context=context)
            print(f"Orchestrator classified intent: '{message}' -> '{intent}'")
            # "tagging",
            # "document_qa",
            if intent == "ingestion":
                target_agent = ingestion_openai_agent
            elif intent in {"analytics", "publishing_insights"}:
                target_agent = analytics_openai_agent
            elif intent in {"query_metrics"}:
                target_agent = analytics_openai_agent
            else:
                logger.warning("Unsupported intent after classification", intent=intent)
                return POLITE_REJECTION

            result = await Runner.run(
                target_agent,
                message,
                session=get_agent_sqlalchemy_session(target_agent.name, context=context),
            )
            if isinstance(result.final_output, str):
                return result.final_output
            if hasattr(result.final_output, "model_dump"):
                return result.final_output.model_dump(mode="json")
            return result.final_output

        except ValueError as e:
            logger.warning("Intent classification failed; stopping routing", error=str(e))
            return {
                "error": "classification_error",
                "message": (
                    "I'm not sure how to handle that request. "
                    "Could you try rephrasing it?"
                ),
            }

        except Exception as e:
            logger.error("Agent execution failed", error=str(e))
            return {
                "error": "agent_error",
                "message": (
                    "Something went wrong while processing your request. "
                    "Please try again, or rephrase your question."
                ),
            }

# Global orchestrator instance
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
