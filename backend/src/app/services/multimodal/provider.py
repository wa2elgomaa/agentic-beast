"""Provider contracts for multimodal realtime chat."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MultimodalProvider(ABC):
    """Abstract provider for realtime multimodal chat runtimes."""

    @abstractmethod
    async def dependency_status(self) -> dict[str, Any]:
        """Return dependency and runtime readiness details."""

    @abstractmethod
    async def create_session(self, user_id: str, conversation_id: str | None = None) -> dict[str, Any]:
        """Create a new realtime multimodal session."""

    @abstractmethod
    async def handle_event(self, session_id: str, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a client event and return server events to emit."""

    @abstractmethod
    async def close_session(self, session_id: str) -> None:
        """Clean up session resources."""