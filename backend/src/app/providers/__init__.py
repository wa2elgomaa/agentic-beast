"""Provider compatibility shim: expose factory helper and legacy symbols."""

from app.logging import get_logger
from app.providers.base import AIProvider
from app.providers.factory import clear_provider_cache, get_ai_provider
from app.providers.openai_provider import OpenAIProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.strands_provider import StrandsProvider

logger = get_logger(__name__)

# Keep a simple compatibility surface for callers that import from
# `app.providers`. Prefer `get_ai_provider(name, model, options)` from
# `app.providers.factory` for new code.

__all__ = [
    "get_ai_provider",
    "clear_provider_cache",
    "AIProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "StrandsProvider",
]
