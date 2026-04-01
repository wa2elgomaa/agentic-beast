"""Model provider factory.

Single responsibility: return the correct Strands model provider based on
``AI_PROVIDER`` in ``.env`` (``settings.ai_provider``), with an optional
``selected_model`` argument to override the model identifier at call time.

Usage::

    from app.agents.agent_factory import get_model_provider

    model = get_model_provider()               # uses AI_PROVIDER + OPENAI_MODEL / OLLAMA_MODEL from .env
    model = get_model_provider("gpt-4o-mini")  # same backend, different model name
"""

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


def get_model_provider(selected_model: Optional[str] = None):
    """Return a Strands-compatible model provider for the configured AI_PROVIDER.

    Args:
        selected_model: Override the model identifier from ``.env``
                        (e.g. ``"gpt-4o"``, ``"mistral"``).  The backend is
                        still determined by ``AI_PROVIDER``.

    Returns:
        A Strands model provider compatible with ``strands.Agent(model=...)``.

    Raises:
        ValueError: When ``AI_PROVIDER`` is not ``"openai"``, ``"strands"``,
                    or ``"ollama"``.
    """
    match settings.ai_provider:
        case "openai":
            from strands.models.openai import OpenAIModel  # noqa: PLC0415

            model_id = selected_model or settings.openai_model
            client_args: dict = {}
            if settings.openai_api_key:
                client_args["api_key"] = settings.openai_api_key

            logger.debug("Building OpenAIModel", model_id=model_id)
            return OpenAIModel(client_args=client_args or None, model_id=model_id)

        case "ollama":
            from strands.models.ollama import OllamaModel  # noqa: PLC0415

            model_id = selected_model or settings.ollama_model
            host = (settings.ollama_base_url or "http://localhost:11434").rstrip("/")

            logger.debug("Building OllamaModel", model_id=model_id, host=host)
            return OllamaModel(host=host, model_id=model_id)

        case _:
            raise ValueError(
                f"Unsupported AI_PROVIDER {settings.ai_provider!r}. "
                "Set AI_PROVIDER to 'openai', 'strands', or 'ollama' in .env."
            )
