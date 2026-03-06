"""Abstract base class for AI providers."""

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel


class Message(BaseModel):
    """Message for AI provider."""

    role: str  # user, assistant
    content: str


class CompletionResponse(BaseModel):
    """Response from AI provider completion."""

    content: str
    model: str
    stop_reason: Optional[str] = None
    usage: Optional[dict] = None


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, model: str):
        """Initialize the provider."""
        self.model = model

    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        """Generate a completion from the AI provider.

        Args:
            messages: List of messages in the conversation.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            Completion response.
        """
        pass

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Generate embeddings for text.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector.
        """
        pass
