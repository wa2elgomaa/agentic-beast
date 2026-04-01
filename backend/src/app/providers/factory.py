"""AI provider factory: create provider instances with optional overrides.

Supported provider names:
    'openai'  -- Bare OpenAI client (direct chat-completions)
    'ollama'  -- Bare Ollama client (local LLM via HTTP)
    'strands' -- Strands-backed provider (wraps strands.Agent; supports openai/ollama as backend)

The factory caches instances by (name, model) key so that repeated calls with
the same configuration return the same object.  Pass `options` to override
API keys, base URLs, embedding models, or Strands backend selection.
"""
from __future__ import annotations

from typing import Dict, Optional

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider

logger = get_logger(__name__)

_CACHE: Dict[str, AIProvider] = {}


def get_ai_provider(
    name: Optional[str] = None,
    model: Optional[str] = None,
    options: Optional[dict] = None,
) -> AIProvider:
    """Return an AI provider instance.

    Args:
        name: Provider name ('openai', 'ollama', 'strands'). Defaults to
              `settings.ai_provider`.
        model: Optional model id override.
        options: Provider-specific kwargs:
            - openai: api_key, embedding_model
            - ollama: base_url, embedding_model
            - strands: backend_name ('openai'|'ollama'), api_key, base_url

    Returns:
        An initialized `AIProvider` instance (cached per name+model key).
    """
    provider_name = name or settings.ai_provider
    cache_key = f"{provider_name}:{model or ''}"

    if cache_key in _CACHE:
        return _CACHE[cache_key]

    opts = options or {}
    inst: AIProvider

    if provider_name == "openai":
        from app.providers.openai_provider import OpenAIProvider  # noqa: PLC0415
        logger.info("Creating OpenAI provider", model=model)
        inst = OpenAIProvider(
            model=model,
            api_key=opts.get("api_key"),
            embedding_model=opts.get("embedding_model"),
        )

    elif provider_name == "ollama":
        from app.providers.ollama_provider import OllamaProvider  # noqa: PLC0415
        logger.info("Creating Ollama provider", model=model)
        inst = OllamaProvider(
            model=model,
            base_url=opts.get("base_url"),
            embedding_model=opts.get("embedding_model"),
        )

    elif provider_name == "strands":
        from app.providers.strands_provider import StrandsProvider  # noqa: PLC0415
        backend = opts.get("backend_name") or settings.ai_provider
        # When ai_provider itself is 'strands', default backend to 'openai'
        if backend == "strands":
            backend = "openai"
        logger.info("Creating Strands provider", backend=backend, model=model)
        inst = StrandsProvider(
            backend_name=backend,
            model_id=model,
            api_key=opts.get("api_key"),
            base_url=opts.get("base_url"),
        )

    else:
        raise ValueError(
            f"Unknown AI provider: {provider_name!r}. "
            "Supported: 'openai', 'ollama', 'strands'."
        )

    _CACHE[cache_key] = inst
    return inst


def clear_provider_cache() -> None:
    """Clear the provider instance cache (useful in tests)."""
    _CACHE.clear()
