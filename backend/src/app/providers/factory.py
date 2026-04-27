"""AI provider factory: create provider instances with optional overrides.

Supported provider names:
    'openai'  -- Bare OpenAI client (direct chat-completions)
    'ollama'  -- Bare Ollama client (local LLM via HTTP)
    'strands' -- Strands-backed provider (wraps strands.Agent; supports openai/ollama as backend)
    'litert' -- LiteRT adapter (exposes minimal session/complete/stream_tts API for multimodal orchestrator)

The factory caches instances by (name, model) key so that repeated calls with
the same configuration return the same object.  Pass `options` to override
API keys, base URLs, embedding models, or Strands backend selection.
"""
from __future__ import annotations

from typing import Dict, Optional
import threading

from app.config import settings, AISettings
import logging
from app.providers.base import AIProvider, Message
from strands.models import Model

logger = logging.getLogger(__name__)

_CACHE: Dict[str, Model] = {}
_CACHE_LOCK = threading.Lock()


def get_ai_provider(
    settings: AISettings = AISettings()
) -> Model:
    """Return an AI provider instance.

    Args:
        name: Provider name ('openai', 'ollama', 'strands', 'litert'). Defaults to
        `settings.main_llm_provider`.
        model: Optional model id override.
        options: Provider-specific kwargs:
            - openai: api_key, embedding_model
            - ollama: base_url, embedding_model
            - strands: backend_name ('openai'|'ollama'), api_key, base_url
            - litert: model
    Returns:
        An initialized `Model` instance (cached per name+model key).
    """
    provider_name = settings.provider or getattr(settings, "main_llm_provider", None)
    if not provider_name:
        # Fall back to global main_agent settings when called with no explicit provider
        from app.config import settings as _global_settings  # noqa: PLC0415
        _fallback = _global_settings.main_agent
        provider_name = _fallback.provider
        if not settings.model_name:
            settings = _fallback
    opts = {}
    # Include relevant options in the cache key so callers that pass a
    # different api_key/base_url do not accidentally receive a cached
    # client configured for another backend.
    cache_key = f"{provider_name}:{settings.model_name or ''}"

    with _CACHE_LOCK:
        if cache_key in _CACHE:
            return _CACHE[cache_key]

    inst: Model

    # Only support the three v1 providers: openai, ollama, litert
    if provider_name == "openai":
        # v1 OpenAI provider exposes a `get_provider(config)` factory
        from app.providers.v1.openai_provider import get_model as get_openai  # noqa: PLC0415
        logger.info("Creating v1 OpenAIResponsesModel", extra={"model": settings.model_name})
        inst = get_openai(settings)

    elif provider_name == "ollama":
        from app.providers.v1.ollama_provider import get_model as get_ollama  # noqa: PLC0415

        logger.info("Creating v1 OllamaModel", extra={"model": settings.model_name})
        inst = get_ollama(settings)

    elif provider_name == "litert":
        from app.providers.v1.litert_provider import get_model as get_litert  # noqa: PLC0415

        logger.info("Creating v1 LiteLLMModel", extra={"model": settings.model_name})
        inst = get_litert(settings)

    else:
        raise ValueError(
            f"Unknown AI provider: {provider_name!r}. Supported: 'openai', 'ollama', 'litert'."
        )

    with _CACHE_LOCK:
        _CACHE[cache_key] = inst
    return inst


def clear_provider_cache() -> None:
    """Clear the provider instance cache (useful in tests)."""
    _CACHE.clear()

class ProviderFactory:
    """Lightweight object wrapper around the provider factory functions.

    Provides an OO API for resolving providers and ensures backward
    compatibility by exposing a `generate()` coroutine on returned
    instances (wrapping providers that only implement `complete()`).
    """

    def __init__(self, agent_settings: AISettings = AISettings()) -> None:
        self._local_cache: Dict[str, AIProvider] = {}
        self.agent_settings = agent_settings

    def get_model(self, settings: Optional[AISettings] = None) -> Model:
        """Return a provider instance by delegating to `get_ai_provider`.

        When `settings` is provided it must include `provider` and
        `model_name` keys; `api_key` and `base_url` are optional.
        """
        # If caller didn't supply settings, prefer the factory's agent_settings
        # if populated, otherwise fallback to global `settings.main_agent`.
        cfg = settings
        if cfg is None:
            cfg = self.agent_settings if isinstance(self.agent_settings, AISettings) else None
        if cfg is None or not getattr(cfg, "provider", None) or not getattr(cfg, "model_name", None):
            # Use global defaults from app.config.settings.main_agent
            global_defaults = __import__("app.config", fromlist=["settings"]).settings
            cfg = cfg or global_defaults.main_agent

        if not isinstance(cfg, AISettings):
            raise TypeError("settings must be an instance of AISettings")

        if missing := [k for k in ("provider", "model_name") if not getattr(cfg, k, None)]:
            raise ValueError(f"settings missing required keys: {missing}")

        return get_ai_provider(cfg)

    def clear_cache(self) -> None:
        """Clear the global provider cache (useful for tests)."""
        clear_provider_cache()

