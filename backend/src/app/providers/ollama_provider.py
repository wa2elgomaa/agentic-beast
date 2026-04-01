"""Ollama local LLM provider implementation."""

import httpx
from typing import List, Optional

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider, CompletionResponse, Message

logger = get_logger(__name__)


class OllamaProvider(AIProvider):
    """Ollama local LLM provider implementation.

    Config-driven: accepts optional model/base_url/embedding_model overrides;
    falls back to `settings` when not provided. This makes it usable both via
    the legacy module-level `get_ai_provider()` call and via the provider factory
    with explicit parameters.

    Installation:
        1. Download from https://ollama.ai
        2. Run: ollama serve
        3. In another terminal: ollama pull mistral
        4. Set AI_PROVIDER=ollama in .env
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        **kwargs,
    ):
        """Initialize Ollama provider.

        Args:
            model: Optional model override (falls back to settings.ollama_model).
            base_url: Optional Ollama base URL override (falls back to settings.ollama_base_url).
            embedding_model: Optional embedding model override (falls back to settings.ollama_embedding_model).
        """
        chosen_model = model or settings.ollama_model
        super().__init__(chosen_model, **kwargs)
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.embedding_model = embedding_model or settings.ollama_embedding_model
        self.client = httpx.AsyncClient(timeout=120.0)
        logger.info(
            "Ollama provider initialized",
            model=self.model,
            base_url=self.base_url,
            embedding_model=self.embedding_model
        )

    async def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        """Generate completion using Ollama local LLM.

        Args:
            messages: List of messages in conversation.
            temperature: Sampling temperature (0-1).
                Lower = deterministic, Higher = creative.
            max_tokens: Maximum tokens in response.
            **kwargs: Additional provider-specific arguments.

        Returns:
            CompletionResponse with generated text.

        Raises:
            RuntimeError: If Ollama server is not running.
            httpx.HTTPError: If API call fails.
        """
        try:
            # Format messages for Ollama API
            formatted_messages = [
                {
                    "role": m.role,
                    "content": m.content
                }
                for m in messages
            ]

            # Build request payload
            payload = {
                "model": self.model,
                "messages": formatted_messages,
                "temperature": temperature,
                "stream": False,  # Get full response at once (not streaming)
            }

            # Add optional max_tokens (Ollama uses "num_predict")
            if max_tokens:
                payload["num_predict"] = max_tokens

            # Log request for debugging
            logger.debug(
                "Ollama completion request",
                model=self.model,
                num_messages=len(messages),
                temperature=temperature
            )

            # Call Ollama API endpoint
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120.0  # Generous timeout for local processing
            )
            response.raise_for_status()

            result = response.json()

            # Extract completion and metadata
            content = result.get("message", {}).get("content", "")
            prompt_tokens = result.get("prompt_eval_count", 0)
            completion_tokens = result.get("eval_count", 0)

            return CompletionResponse(
                content=content,
                model=self.model,
                stop_reason="end_turn" if result.get("done") else "continue",
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                }
            )

        except httpx.ConnectError as e:
            error_msg = (
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Make sure Ollama is running: 'ollama serve'"
            )
            logger.error("Ollama connection error", error=str(e), hint=error_msg)
            raise RuntimeError(error_msg) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_msg = (
                    f"Model '{self.model}' not found in Ollama. "
                    f"Pull it with: 'ollama pull {self.model}'"
                )
                logger.error("Ollama model not found", model=self.model, error=str(e))
                raise RuntimeError(error_msg) from e
            logger.error("Ollama HTTP error", status=e.response.status_code, error=str(e))
            raise

        except Exception as e:
            logger.error(
                "Ollama completion error",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def embed(self, text: str) -> List[float]:
        """Generate embeddings using Ollama.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats.

        Raises:
            RuntimeError: If Ollama server is not running.
            httpx.HTTPError: If API call fails.
        """
        try:
            logger.debug(
                "Ollama embedding request",
                model=self.embedding_model,
                text_length=len(text)
            )

            response = await self.client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.embedding_model,
                    "prompt": text
                },
                timeout=60.0
            )
            response.raise_for_status()

            result = response.json()
            embedding = result.get("embedding", [])

            if not embedding:
                logger.warning("Empty embedding returned from Ollama")

            return embedding

        except httpx.ConnectError as e:
            error_msg = (
                f"Cannot connect to Ollama at {self.base_url} for embeddings. "
                f"Make sure Ollama is running: 'ollama serve'"
            )
            logger.error("Ollama connection error for embeddings", error=str(e))
            raise RuntimeError(error_msg) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_msg = (
                    f"Embedding model '{self.embedding_model}' not found. "
                    f"Pull it with: 'ollama pull {self.embedding_model}'"
                )
                logger.error("Ollama embedding model not found", error=str(e))
                raise RuntimeError(error_msg) from e
            logger.error("Ollama embedding HTTP error", status=e.response.status_code, error=str(e))
            raise

        except Exception as e:
            logger.error(
                "Ollama embedding error",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def close(self):
        """Close HTTP client connection.

        Call this during shutdown to clean up resources.
        """
        if self.client:
            await self.client.aclose()
            logger.debug("Ollama HTTP client closed")


__all__ = ["OllamaProvider"]
