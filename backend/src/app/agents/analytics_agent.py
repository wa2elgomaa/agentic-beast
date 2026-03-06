"""Analytics agent for processing natural language analytics queries."""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentCapability, BaseAgent
from app.logging import get_logger
from app.providers.base import Message
from app.schemas.analytics import (
    Aggregation,
    DateRange,
    MetricName,
    AnalyticsQuery,
    GroupBy,
)
from app.tools.analytics_tools import AnalyticsTools

logger = get_logger(__name__)


class AnalyticsAgent(BaseAgent):
    """Agent for processing analytics queries."""

    def __init__(self, db_session: AsyncSession):
        """Initialize analytics agent."""
        super().__init__(
            name="analytics_agent",
            description="Agent for analyzing social media analytics data",
        )
        self.db = db_session
        self.tools = AnalyticsTools(db_session)

        # Register capabilities
        self.capabilities = [
            AgentCapability(
                name="query_metrics",
                description="Query analytics metrics like reach, impressions, engagement",
                required_tools=["execute_query"],
            ),
            AgentCapability(
                name="compare_platforms",
                description="Compare performance across platforms",
                required_tools=["execute_query"],
            ),
            AgentCapability(
                name="publishing_insights",
                description="Get recommendations for best publishing times",
                required_tools=["get_publishing_insights"],
            ),
        ]

    async def execute(self, user_message: str, **kwargs) -> str:
        """Execute agent logic.

        Args:
            user_message: Input message from user.

        Returns:
            Response message.
        """
        logger.info("Analytics agent processing message", message_length=len(user_message))

        # Intent detection (simple keyword-based for now)
        intent = self._classify_intent(user_message)
        context = self._extract_context(user_message)

        try:
            response = await self.handle_intent(intent, context)
            await self.save_state({"last_query": user_message, "last_intent": intent})
            return response
        except Exception as e:
            logger.error("Analytics agent error", error=str(e), intent=intent)
            self.health_status.status = "error"
            self.health_status.error = str(e)
            return f"I encountered an error processing your analytics query: {str(e)}"

    async def handle_intent(self, intent: str, context: Dict[str, Any]) -> str:
        """Handle a specific intent.

        Args:
            intent: Classified user intent.
            context: Contextual information.

        Returns:
            Response message.
        """
        if intent == "query_metrics":
            return await self._handle_metrics_query(context)
        elif intent == "compare_platforms":
            return await self._handle_platform_comparison(context)
        elif intent == "publishing_insights":
            return await self._handle_publishing_insights(context)
        else:
            return "I'm not sure how to analyze that. Please ask about metrics, platform comparisons, or publishing insights."

    async def _handle_metrics_query(self, context: Dict[str, Any]) -> str:
        """Handle metrics query."""
        try:
            # Build query from context
            metric_name = context.get("metric", MetricName.REACH)
            start_date = context.get("start_date")
            end_date = context.get("end_date")
            platform = context.get("platform")

            if not start_date or not end_date:
                return "I need a date range to query. Please specify a start and end date."

            query = AnalyticsQuery(
                metric_name=metric_name,
                aggregation=context.get("aggregation", Aggregation.SUM),
                date_range=DateRange(start_date=start_date, end_date=end_date),
                platform=platform,
                group_by=[GroupBy.PLATFORM] if not platform else None,
            )

            result = await self.tools.execute_query(query)

            # Format response
            response = f"Analytics for {metric_name.value}:\n"
            for row in result.rows[:5]:  # Top 5 results
                response += f"  - {row.metric_value:,.0f}"
                if row.platform:
                    response += f" ({row.platform})"
                response += "\n"

            if len(result.rows) > 5:
                response += f"  ... and {len(result.rows) - 5} more results"

            return response

        except Exception as e:
            logger.error("Metrics query error", error=str(e))
            return f"Error querying metrics: {str(e)}"

    async def _handle_platform_comparison(self, context: Dict[str, Any]) -> str:
        """Handle platform comparison query."""
        try:
            metric_name = context.get("metric", MetricName.REACH)
            start_date = context.get("start_date")
            end_date = context.get("end_date")

            if not start_date or not end_date:
                return "I need a date range to compare. Please specify a start and end date."

            query = AnalyticsQuery(
                metric_name=metric_name,
                aggregation=Aggregation.SUM,
                date_range=DateRange(start_date=start_date, end_date=end_date),
                group_by=[GroupBy.PLATFORM],
            )

            result = await self.tools.execute_query(query)

            response = f"Platform comparison for {metric_name.value}:\n"
            for row in sorted(result.rows, key=lambda x: x.metric_value, reverse=True):
                response += f"  {row.platform}: {row.metric_value:,.0f}\n"

            return response

        except Exception as e:
            logger.error("Platform comparison error", error=str(e))
            return f"Error comparing platforms: {str(e)}"

    async def _handle_publishing_insights(self, context: Dict[str, Any]) -> str:
        """Handle publishing insights query."""
        try:
            platform = context.get("platform", "instagram")

            insights = await self.tools.get_publishing_insights(platform)

            response = f"Publishing insights for {platform}:\n"
            for insight in insights[:3]:  # Top 3
                response += (
                    f"  {insight.best_day_of_week}: "
                    f"{insight.average_engagement:.1f} avg engagement "
                    f"({insight.sample_size} posts)\n"
                )

            return response

        except Exception as e:
            logger.error("Publishing insights error", error=str(e))
            return f"Error getting publishing insights: {str(e)}"

    def _classify_intent(self, message: str) -> str:
        """Classify user intent from message.

        Args:
            message: User message.

        Returns:
            Intent classification.
        """
        message_lower = message.lower()

        if "publish" in message_lower and ("best" in message_lower or "time" in message_lower):
            return "publishing_insights"
        elif "compare" in message_lower and "platform" in message_lower:
            return "compare_platforms"
        else:
            return "query_metrics"

    def _extract_context(self, message: str) -> Dict[str, Any]:
        """Extract contextual information from message.

        Args:
            message: User message.

        Returns:
            Dictionary with extracted context.
        """
        from datetime import date, timedelta

        context = {}

        # Simple date extraction
        message_lower = message.lower()
        if "last week" in message_lower:
            context["end_date"] = date.today()
            context["start_date"] = date.today() - timedelta(days=7)
        elif "last month" in message_lower:
            context["end_date"] = date.today()
            context["start_date"] = date.today() - timedelta(days=30)
        else:
            context["start_date"] = date.today() - timedelta(days=30)
            context["end_date"] = date.today()

        # Platform detection
        for platform in ["instagram", "tiktok", "youtube", "facebook", "twitter"]:
            if platform in message_lower:
                context["platform"] = platform
                break

        # Metric detection
        for metric in ["reach", "impressions", "engagement", "likes", "comments"]:
            if metric in message_lower:
                context["metric"] = MetricName.REACH if metric == "reach" else MetricName.IMPRESSIONS
                break

        return context
