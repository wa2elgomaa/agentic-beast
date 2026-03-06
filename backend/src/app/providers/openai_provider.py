"""OpenAI provider implementation."""

from typing import List, Optional

from openai import AsyncOpenAI, RateLimitError

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider, CompletionResponse, Message

logger = get_logger(__name__)


class OpenAIProvider(AIProvider):
    """OpenAI API provider implementation."""

    def __init__(self):
        """Initialize OpenAI provider."""
        super().__init__(settings.openai_model)
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        logger.info("OpenAI provider initialized", model=self.model)

    async def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        """Generate a completion using OpenAI API.

        Args:
            messages: List of messages in the conversation.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            Completion response.
        """
        try:
            # Convert Message objects to dict format for OpenAI
            messages_dict = [{"role": m.role, "content": m.content} for m in messages]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages_dict,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

            return CompletionResponse(
                content=response.choices[0].message.content,
                model=response.model,
                stop_reason=response.choices[0].finish_reason,
                usage=response.usage.model_dump() if response.usage else None,
            )

        except RateLimitError as e:
            logger.warning("OpenAI rate limit exceeded", error=str(e))
            raise
        except Exception as e:
            logger.error("OpenAI completion error", error=str(e))
            raise

    async def embed(self, text: str) -> List[float]:
        """Generate embeddings using OpenAI API.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector.
        """
        try:
            response = await self.client.embeddings.create(
                model=settings.openai_embedding_model,
                input=text,
            )

            return response.data[0].embedding

        except Exception as e:
            logger.error("OpenAI embedding error", error=str(e))
            raise
