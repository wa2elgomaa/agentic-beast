"""Provider compatibility shim: expose factory helper and legacy symbols."""

from app.providers.base import AIProvider
from app.providers.factory import clear_provider_cache, get_ai_provider
from app.providers.v1.openai_provider import get_model as get_openai_model
from app.providers.v1.ollama_provider import get_model as get_ollama_model
from app.providers.v1.litert_provider import get_model as get_litellm_model


# Keep a simple compatibility surface for callers that import from
# `app.providers`. Prefer `get_ai_provider(name, model, options)` from
# `app.providers.factory` for new code.

__all__ = [
    "get_ai_provider",
    "clear_provider_cache",
    "AIProvider",
    "get_openai_model",
    "get_ollama_model",
    "get_litellm_model",
]
