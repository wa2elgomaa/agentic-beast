"""Abstract base class for AI providers."""

import asyncio
import random
import time
from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel

import logging

logger = logging.getLogger(__name__)


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

    def __init__(self, model: str, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        """Initialize the provider.
        
        Args:
            model: The model identifier.
            max_retries: Maximum number of retries on rate limit/error.
            base_delay: Base delay for exponential backoff (seconds).
            max_delay: Maximum delay for exponential backoff (seconds).
        """
        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def _retry_with_backoff(self, operation, *args, **kwargs):
        """Retry an operation with exponential backoff.
        
        Args:
            operation: Async operation to retry.
            *args, **kwargs: Arguments to pass to the operation.
            
        Returns:
            Result of the operation.
            
        Raises:
            Exception: If all retries are exhausted.
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                # Check if this is a retryable error (rate limiting, temporary failures)
                if not self._is_retryable_error(e):
                    logger.error(
                        "Non-retryable error",
                        extra={"error": str(e), "error_type": type(e).__name__},
                    )
                    raise e
                
                if attempt == self.max_retries:
                    logger.error(
                        "Max retries exhausted",
                        extra={"attempts": attempt + 1, "error": str(e)},
                    )
                    break
                
                # Calculate delay with exponential backoff and jitter
                delay = min(
                    self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                    self.max_delay
                )
                
                logger.warning(
                    "Retrying operation",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "delay": delay,
                        "error": str(e),
                    },
                )
                
                await asyncio.sleep(delay)
        
        # `last_exception` should be set if we exited the retry loop due to
        # an exception. Defensive check for static type-checkers and any
        # unexpected control flow: raise a RuntimeError if not present.
        if last_exception is None:
            raise RuntimeError("Retry loop exited without an exception")
        raise last_exception

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable.
        
        Args:
            error: The exception to check.
            
        Returns:
            True if the error is retryable, False otherwise.
        """
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Common retryable error patterns
        retryable_patterns = [
            "rate limit", "rate_limit", "too many requests", "quota exceeded",
            "timeout", "connection", "network", "502", "503", "504"
        ]
        
        return any(pattern in error_str for pattern in retryable_patterns) or error_type in [
            "TimeoutError", "ConnectionError", "HTTPStatusError"
        ]

    async def complete_with_retry(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        """Generate a completion with automatic retry logic.
        
        Args:
            messages: List of messages in the conversation.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            **kwargs: Additional provider-specific arguments.
            
        Returns:
            Completion response.
        """
        return await self._retry_with_backoff(
            self.complete,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

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
