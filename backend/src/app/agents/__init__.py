"""Agent framework — v1 agent implementations."""

from app.agents.v1.classify_agent import ClassifyAgent, get_agent as get_classify_agent
from app.agents.v1.chat_agent import ChatAgent, get_agent as get_chat_agent
from app.agents.v1.analytics_agent import AnalyticsAgent, get_agent as get_analytics_agent
from app.agents.v1.orchestrator_agent import OrchestratorAgent, get_agent as get_orchestrator
from app.agents.tagging_agent import TaggingAgent, get_agent as get_tagging_agent
from app.agents.recommendation_agent import RecommendationAgent, get_agent as get_recommendation_agent
from app.agents.document_agent import DocumentAgent, get_agent as get_document_agent
from app.agents.general_agent import GeneralAgent, get_agent as get_general_agent

__all__ = [
    "ClassifyAgent", "get_classify_agent",
    "ChatAgent", "get_chat_agent",
    "AnalyticsAgent", "get_analytics_agent",
    "OrchestratorAgent", "get_orchestrator",
    "TaggingAgent", "get_tagging_agent",
    "RecommendationAgent", "get_recommendation_agent",
    "DocumentAgent", "get_document_agent",
    "GeneralAgent", "get_general_agent",
]
