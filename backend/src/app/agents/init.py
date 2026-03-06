"""Agent and adapter initialization and registration."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gmail_adapter import GmailAdapter
from app.adapters.registry import register_adapter
from app.agents.analytics_agent import AnalyticsAgent
from app.agents.ingestion_agent import IngestionAgent
from app.agents.orchestrator import get_orchestrator
from app.logging import get_logger

logger = get_logger(__name__)


async def initialize_adapters() -> None:
    """Initialize and register all data adapters."""
    logger.info("Initializing adapters")

    # Register Gmail adapter
    register_adapter("gmail", GmailAdapter)
    logger.info("Adapters initialized successfully")


async def initialize_agents(db_session: AsyncSession) -> None:
    """Initialize and register all agents with the orchestrator.

    Args:
        db_session: Database session for agents to use.
    """
    orchestrator = get_orchestrator()

    logger.info("Initializing agents")

    # Create analytics agent
    analytics_agent = AnalyticsAgent(db_session)
    await analytics_agent.connect()

    # Register analytics agent with its intents
    orchestrator.register_agent(
        analytics_agent,
        intents=[
            "query_metrics",
            "analytics",
            "reach",
            "impressions",
            "engagement",
            "compare_platforms",
            "platform_comparison",
            "publishing_insights",
            "best_time_publish",
        ],
    )

    # Create ingestion agent
    ingestion_agent = IngestionAgent(db_session)
    await ingestion_agent.connect()

    # Register ingestion agent with its intents
    orchestrator.register_agent(
        ingestion_agent,
        intents=[
            "ingest",
            "process",
            "import",
            "upload",
            "trigger",
            "ingestion",
            "check_status",
            "status",
        ],
    )

    # Set analytics as default agent for unmatched queries
    orchestrator.set_default_agent("analytics_agent")

    logger.info("Agents initialized successfully")
