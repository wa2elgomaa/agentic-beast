"""Agent framework — v1 agent implementations."""

from app.agents.v1.classify_agent import ClassifyAgent, get_agent as get_classify_agent
from app.agents.v1.chat_agent import ChatAgent, get_agent as get_chat_agent
from app.agents.v1.analytics_agent import AnalyticsAgent, get_agent as get_analytics_agent
from app.agents.v1.orchestrator_agent import OrchestratorAgent, get_agent as get_orchestrator

__all__ = [
    "ClassifyAgent", "get_classify_agent",
    "ChatAgent", "get_chat_agent",
    "AnalyticsAgent", "get_analytics_agent",
    "OrchestratorAgent", "get_orchestrator",
]
