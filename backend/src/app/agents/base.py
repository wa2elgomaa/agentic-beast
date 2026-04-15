"""Base agent interface for Strands Agents SDK."""

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


class AgentCapability:
    """Defines an agent's capability."""

    def __init__(self, name: str, description: str, required_tools: List[str]):
        """Initialize capability."""
        self.name = name
        self.description = description
        self.required_tools = required_tools


class AgentHealthStatus:
    """Health status of an agent."""

    def __init__(self, status: str = "healthy", error: Optional[str] = None):
        """Initialize health status."""
        self.status = status
        self.error = error
        self.last_check = datetime.now(timezone.utc)


class BaseAgent(ABC):
    """Abstract base class for all agents in the Strands Agents SDK pattern."""

    def __init__(self, name: str, description: str):
        """Initialize the agent.

        Args:
            name: Unique agent identifier.
            description: Human-readable agent description.
        """
        self.name = name
        self.description = description
        self.agent_id = str(uuid.uuid4())
        self.capabilities: List[AgentCapability] = []
        self.health_status = AgentHealthStatus()
        self._redis: Optional[redis.Redis] = None

    @property
    async def redis(self) -> redis.Redis:
        """Get or create Redis connection for state management."""
        if self._redis is None:
            self._redis = await redis.from_url(settings.redis_url)
        return self._redis

    async def connect(self) -> None:
        """Establish agent connections (Redis, etc.)."""
        try:
            self._redis = await redis.from_url(settings.redis_url)
            await self._redis.ping()
            logger.info("Agent connected to Redis", agent_name=self.name)
        except Exception as e:
            logger.error("Failed to connect agent to Redis", agent_name=self.name, error=str(e))
            self.health_status = AgentHealthStatus(status="error", error=str(e))

    async def disconnect(self) -> None:
        """Close agent connections."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Agent disconnected from Redis", agent_name=self.name)

    async def save_state(self, state: Dict[str, Any], ttl_hours: int = 24) -> None:
        """Save agent state to Redis.

        Args:
            state: State dictionary to save.
            ttl_hours: Time-to-live in hours.
        """
        try:
            redis_client = await self.redis
            state_key = f"agent:{self.agent_id}:state"
            await redis_client.setex(
                state_key,
                timedelta(hours=ttl_hours),
                json.dumps(state),
            )
            logger.debug("Agent state saved", agent_name=self.name, state_key=state_key)
        except Exception as e:
            logger.error("Failed to save agent state", agent_name=self.name, error=str(e))

    async def load_state(self) -> Dict[str, Any]:
        """Load agent state from Redis.

        Returns:
            State dictionary, or empty dict if not found.
        """
        try:
            redis_client = await self.redis
            state_key = f"agent:{self.agent_id}:state"
            state_json = await redis_client.get(state_key)
            if state_json:
                return json.loads(state_json)
            return {}
        except Exception as e:
            logger.error("Failed to load agent state", agent_name=self.name, error=str(e))
            return {}

    async def save_health_status(self) -> None:
        """Save health status to Redis."""
        try:
            redis_client = await self.redis
            health_key = f"agent:{self.agent_id}:health"
            health_data = {
                "status": self.health_status.status,
                "error": self.health_status.error,
                "last_check": self.health_status.last_check.isoformat(),
            }
            await redis_client.setex(
                health_key,
                timedelta(hours=1),
                json.dumps(health_data),
            )
        except Exception as e:
            logger.error("Failed to save health status", agent_name=self.name, error=str(e))

    @abstractmethod
    async def execute(self, intent: str, user_message: str, **kwargs) -> str:
        """Execute agent logic.

        Args:
            intent: Classified user intent.
            user_message: Input message from user.

        Returns:
            Response message from agent.
        """
        pass

    @abstractmethod
    async def handle_intent(self, intent: str, context: Dict[str, Any]) -> str:
        """Handle a specific intent.

        Args:
            intent: Classified user intent.
            context: Contextual information.

        Returns:
            Response message.
        """
        pass

    async def get_health_status(self) -> AgentHealthStatus:
        """Get current health status."""
        return self.health_status

    async def __aenter__(self):
        """Async context manager enter."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
