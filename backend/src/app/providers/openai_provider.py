"""OpenAI provider implementation."""

from typing import List, Optional

from openai import AsyncOpenAI, RateLimitError

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider, CompletionResponse, Message

logger = get_logger(__name__)


class OpenAIProvider(AIProvider):
    """OpenAI API provider implementation.

    This provider is configurable via the factory; it accepts optional
    `model`, `api_key`, and `embedding_model` parameters. If not provided
    it falls back to values from `settings` for backwards compatibility.
    """

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, embedding_model: Optional[str] = None, **kwargs):
        """Initialize OpenAI provider.

        Args:
            model: Optional model id override.
            api_key: Optional API key override.
            embedding_model: Optional embedding model id override.
        """
        chosen_model = model or settings.openai_model
        super().__init__(chosen_model, **kwargs)
        self.client = AsyncOpenAI(
            api_key=api_key or settings.effective_openai_api_key,
            base_url=settings.effective_openai_base_url,
        )
        self.embedding_model = embedding_model or getattr(settings, "openai_embedding_model", None)
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
                model=self.embedding_model or settings.openai_embedding_model,
                input=text,
            )

            return response.data[0].embedding

        except Exception as e:
            logger.error("OpenAI embedding error", error=str(e))
            raise
