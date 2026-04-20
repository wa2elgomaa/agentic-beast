"""Strands-backed AI provider adapter.

Wraps the `strands-agents` SDK to implement our `AIProvider` interface,
supporting OpenAI and Ollama as underlying model backends.  New code should
prefer this provider over the bare `OpenAIProvider` / `OllamaProvider` when
agent-style reasoning is needed; use the bare providers only when you just
need a single completion call.

Usage (via factory):
    provider = get_ai_provider("strands")
    resp = await provider.complete(messages, temperature=0.1)

Model backend is derived automatically from `settings.ai_provider` and the
corresponding API key / base-URL settings, unless caller passes explicit
`backend_name` / `model_id` parameters.
"""

from __future__ import annotations

from typing import List, Optional

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider, CompletionResponse, Message

logger = get_logger(__name__)


class StrandsProvider(AIProvider):
    """AIProvider implementation backed by the Strands Agents SDK.

    Delegates completion calls to a one-shot `strands.Agent` configured with
    either an OpenAI or Ollama Strands model provider.  Embedding always uses
    the underlying bare provider (OpenAIProvider / OllamaProvider) because
    Strands does not yet expose a unified embedding API.

    Args:
        backend_name: Which Strands model backend to use ('openai' or 'ollama').
                      Defaults to `settings.ai_provider` (or 'openai' when
                      ai_provider is 'strands').
        model_id: Model identifier to pass to the Strands model provider.
                  Defaults to the relevant settings value.
        api_key: API key override for OpenAI backend.
        base_url: Base URL override for Ollama backend.
    """

    def __init__(
        self,
        backend_name: Optional[str] = None,
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ) -> None:
        # Resolve backend
        raw_provider = backend_name or settings.ai_provider
        self._backend = "openai" if raw_provider in ("openai", "strands") else raw_provider

        # Resolve model_id
        if model_id:
            resolved_model = model_id
        elif self._backend == "openai":
            resolved_model = settings.openai_model
        else:
            resolved_model = settings.ollama_model

        super().__init__(resolved_model, **kwargs)

        # Build the Strands model lazily to avoid import overhead at module load
        self._strands_model = self._build_strands_model(
            api_key=api_key,
            base_url=base_url,
        )

        # Lazy-init bare provider for embedding delegation
        self._embed_provider: Optional[AIProvider] = None

        logger.info(
            "StrandsProvider initialized",
            backend=self._backend,
            model=self.model,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_strands_model(self, api_key: Optional[str], base_url: Optional[str]):
        """Build and return the appropriate Strands model provider instance."""
        if self._backend == "openai":
            from strands.models.openai import OpenAIModel  # noqa: PLC0415

            client_args: dict = {}
            resolved_key = api_key or settings.effective_openai_api_key
            if resolved_key:
                client_args["api_key"] = resolved_key
            client_args["base_url"] = settings.effective_openai_base_url

            return OpenAIModel(
                client_args=client_args or None,
                model_id=self.model,
            )

        if self._backend == "ollama":
            from strands.models.ollama import OllamaModel  # noqa: PLC0415

            resolved_host = (base_url or settings.ollama_base_url).rstrip("/")
            return OllamaModel(
                host=resolved_host,
                model_id=self.model,
            )

        raise ValueError(f"Unsupported Strands backend: {self._backend!r}")

    def _get_embed_provider(self) -> AIProvider:
        """Return (or lazily create) the bare provider used for embeddings."""
        if self._embed_provider is None:
            if self._backend == "openai":
                from app.providers.openai_provider import OpenAIProvider  # noqa: PLC0415

                self._embed_provider = OpenAIProvider(model=self.model)
            else:
                from app.providers.ollama_provider import OllamaProvider  # noqa: PLC0415

                self._embed_provider = OllamaProvider(model=self.model)
        return self._embed_provider

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        """Run a one-shot Strands Agent to produce a completion.

        The agent is created fresh per call so there is no cross-call state.
        System messages are joined into a single `system_prompt`; all others
        are passed as the user turn.
        """
        from strands import Agent  # noqa: PLC0415

        system_parts = [m.content for m in messages if m.role == "system"]
        user_parts = [m.content for m in messages if m.role != "system"]

        system_prompt = "\n\n".join(system_parts) if system_parts else None
        user_input = "\n\n".join(user_parts) if user_parts else ""

        # Build model with per-call temperature override if supported
        model_kwargs: dict = {}
        if temperature != 0.7:
            model_kwargs["temperature"] = temperature
        if max_tokens is not None:
            model_kwargs["max_tokens"] = max_tokens

        try:
            strands_model = self._strands_model
            if model_kwargs:
                # Rebuild model with overrides when params differ from defaults
                if self._backend == "openai":
                    from strands.models.openai import OpenAIModel  # noqa: PLC0415

                    params: dict = {}
                    if temperature != 0.7:
                        params["temperature"] = temperature
                    if max_tokens is not None:
                        params["max_tokens"] = max_tokens
                    client_args: dict = {}
                    key = settings.effective_openai_api_key
                    if key:
                        client_args["api_key"] = key
                    client_args["base_url"] = settings.effective_openai_base_url
                    strands_model = OpenAIModel(
                        client_args=client_args or None,
                        model_id=self.model,
                        params=params or None,
                    )
                elif self._backend == "ollama":
                    from strands.models.ollama import OllamaModel  # noqa: PLC0415

                    extra: dict = {}
                    if temperature != 0.7:
                        extra["temperature"] = temperature
                    if max_tokens is not None:
                        extra["max_tokens"] = max_tokens
                    strands_model = OllamaModel(
                        host=(settings.ollama_base_url).rstrip("/"),
                        model_id=self.model,
                        **extra,
                    )

            agent = Agent(
                model=strands_model,
                system_prompt=system_prompt,
                callback_handler=None,
            )

            result = await agent.invoke_async(user_input)
            text = str(result)

            return CompletionResponse(
                content=text,
                model=self.model,
                stop_reason="end_turn",
            )

        except Exception as e:
            logger.error("StrandsProvider completion error", error=str(e), backend=self._backend)
            raise

    async def embed(self, text: str) -> List[float]:
        """Delegate embedding to the bare provider (OpenAI or Ollama)."""
        return await self._get_embed_provider().embed(text)
