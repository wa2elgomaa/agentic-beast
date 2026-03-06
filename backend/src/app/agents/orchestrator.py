"""Agent orchestrator for routing and agent coordination."""

from typing import Dict, List, Optional

from app.agents.base import BaseAgent
from app.logging import get_logger

logger = get_logger(__name__)


class AgentOrchestrator:
    """Orchestrator for managing multiple agents and routing intents."""

    def __init__(self):
        """Initialize the orchestrator."""
        self.agents: Dict[str, BaseAgent] = {}
        self.intent_routing: Dict[str, str] = {}  # intent -> agent_name
        self.default_agent: Optional[str] = None

    def register_agent(self, agent: BaseAgent, intents: List[str]) -> None:
        """Register an agent and its intents.

        Args:
            agent: The agent to register.
            intents: List of intents this agent can handle.
        """
        self.agents[agent.name] = agent
        for intent in intents:
            self.intent_routing[intent] = agent.name
        logger.info(
            "Agent registered with orchestrator",
            agent_name=agent.name,
            intent_count=len(intents),
        )

    def set_default_agent(self, agent_name: str) -> None:
        """Set the default agent for unmatched intents.

        Args:
            agent_name: Name of the default agent.
        """
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not registered")
        self.default_agent = agent_name
        logger.info("Default agent set", agent_name=agent_name)

    async def route_to_agent(self, intent: str, context: Dict) -> str:
        """Route an intent to the appropriate agent.

        Args:
            intent: The classified user intent.
            context: Contextual information for the agent.

        Returns:
            Response from the agent.
        """
        agent_name = self.intent_routing.get(intent, self.default_agent)

        if not agent_name:
            logger.warning("No agent found for intent and no default agent set", intent=intent)
            return "I'm not sure how to help with that. Please try a different question."

        if agent_name not in self.agents:
            logger.warning("Agent not found", agent_name=agent_name, intent=intent)
            return "An error occurred while processing your request."

        agent = self.agents[agent_name]
        logger.info("Routing intent to agent", intent=intent, agent_name=agent_name)

        try:
            response = await agent.handle_intent(intent, context)
            return response
        except Exception as e:
            logger.error(
                "Agent execution failed",
                agent_name=agent_name,
                intent=intent,
                error=str(e),
            )
            return "An error occurred while processing your request. Please try again."

    async def get_agent_capabilities(self) -> Dict[str, List[str]]:
        """Get capabilities of all registered agents.

        Returns:
            Dictionary mapping agent names to their capabilities.
        """
        capabilities = {}
        for name, agent in self.agents.items():
            capabilities[name] = [cap.name for cap in agent.capabilities]
        return capabilities

    async def health_check(self) -> Dict[str, Dict]:
        """Get health status of all agents.

        Returns:
            Dictionary with health status of each agent.
        """
        health_status = {}
        for name, agent in self.agents.items():
            status = await agent.get_health_status()
            health_status[name] = {
                "status": status.status,
                "error": status.error,
                "last_check": status.last_check.isoformat(),
            }
        return health_status


# Global orchestrator instance
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
