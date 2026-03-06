"""Ingestion agent for handling data ingestion queries."""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentCapability, BaseAgent
from app.logging import get_logger
from app.services.ingestion_service import get_ingestion_service
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)


class IngestionAgent(BaseAgent):
    """Agent for handling data ingestion operations."""

    def __init__(self, db_session: AsyncSession):
        """Initialize ingestion agent."""
        super().__init__(
            name="ingestion_agent",
            description="Agent for managing data ingestion from external sources",
        )
        self.db = db_session
        self.service = get_ingestion_service(db_session)

        # Register capabilities
        self.capabilities = [
            AgentCapability(
                name="trigger_ingestion",
                description="Trigger data ingestion from Gmail or other sources",
                required_tools=["trigger_email_monitor"],
            ),
            AgentCapability(
                name="check_status",
                description="Check ingestion task status",
                required_tools=["get_task_status"],
            ),
        ]

    async def execute(self, user_message: str, **kwargs) -> str:
        """Execute agent logic.

        Args:
            user_message: Input message from user.

        Returns:
            Response message.
        """
        logger.info("Ingestion agent processing message", message_length=len(user_message))

        # Intent detection
        intent = self._classify_intent(user_message)
        context = self._extract_context(user_message)

        try:
            response = await self.handle_intent(intent, context)
            await self.save_state({"last_query": user_message, "last_intent": intent})
            return response
        except Exception as e:
            logger.error("Ingestion agent error", error=str(e), intent=intent)
            self.health_status.status = "error"
            self.health_status.error = str(e)
            return f"Error processing ingestion request: {str(e)}"

    async def handle_intent(self, intent: str, context: Dict[str, Any]) -> str:
        """Handle a specific intent.

        Args:
            intent: Classified user intent.
            context: Contextual information.

        Returns:
            Response message.
        """
        if intent == "trigger":
            return await self._handle_trigger_ingestion(context)
        elif intent == "status":
            return await self._handle_status_check(context)
        else:
            return "I can help you trigger data ingestion or check ingestion status. What would you like to do?"

    async def _handle_trigger_ingestion(self, context: Dict[str, Any]) -> str:
        """Handle ingestion trigger request."""
        try:
            source = context.get("source", "gmail")
            logger.info("Triggering ingestion", source=source)

            # Queue the appropriate task
            if source == "gmail":
                task = celery_app.send_task("app.tasks.email_monitor.monitor_gmail_inbox")
            else:
                return f"Unknown ingestion source: {source}. Please use 'gmail'."

            return (
                f"✓ Ingestion from {source} has been queued. "
                f"Task ID: {task.id}. "
                f"Check status with 'check ingestion status {task.id}'"
            )

        except Exception as e:
            logger.error("Ingestion trigger failed", error=str(e))
            return f"Failed to trigger ingestion: {str(e)}"

    async def _handle_status_check(self, context: Dict[str, Any]) -> str:
        """Handle ingestion status check request."""
        try:
            task_id = context.get("task_id")
            if not task_id:
                return "Please provide a task ID to check status. Example: 'check status of task <task-id>'"

            task = celery_app.AsyncResult(task_id)

            if task.state == "PENDING":
                return f"Task {task_id}: Status is QUEUED. The task is waiting to be processed."
            elif task.state == "PROGRESS":
                return f"Task {task_id}: Status is PROCESSING. Details: {task.info}"
            elif task.state == "SUCCESS":
                result = task.result
                return (
                    f"Task {task_id}: Status is COMPLETED.\n"
                    f"  Rows inserted: {result.get('inserted', 0)}\n"
                    f"  Rows updated: {result.get('updated', 0)}\n"
                    f"  Rows failed: {result.get('failed', 0)}"
                )
            elif task.state == "FAILURE":
                return f"Task {task_id}: Status is FAILED. Error: {str(task.info)}"
            else:
                return f"Task {task_id}: Status is {task.state}"

        except Exception as e:
            logger.error("Status check failed", error=str(e))
            return f"Failed to check status: {str(e)}"

    def _classify_intent(self, message: str) -> str:
        """Classify user intent from message."""
        message_lower = message.lower()

        if "status" in message_lower or "check" in message_lower or "progress" in message_lower:
            return "status"
        elif "ingest" in message_lower or "process" in message_lower or "import" in message_lower:
            return "trigger"
        else:
            return "help"

    def _extract_context(self, message: str) -> Dict[str, Any]:
        """Extract contextual information from message."""
        context = {}

        # Extract source
        message_lower = message.lower()
        if "gmail" in message_lower:
            context["source"] = "gmail"
        else:
            context["source"] = "gmail"  # Default

        # Extract task ID if present
        import re

        task_id_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", message_lower)
        if task_id_match:
            context["task_id"] = task_id_match.group(0)

        return context
