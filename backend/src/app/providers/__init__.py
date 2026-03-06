"""AI provider factory and implementations."""

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider
from app.providers.bedrock_provider import BedrockProvider
from app.providers.openai_provider import OpenAIProvider

logger = get_logger(__name__)


def get_ai_provider() -> AIProvider:
    """Get the configured AI provider instance.
    
    Returns:
        An AI provider instance based on configuration.
    """
    if settings.ai_provider == "openai":
        logger.info("Using OpenAI provider")
        return OpenAIProvider()
    elif settings.ai_provider == "bedrock":
        logger.info("Using AWS Bedrock provider")
        return BedrockProvider()
    else:
        raise ValueError(f"Unknown AI provider: {settings.ai_provider}")


__all__ = ["get_ai_provider", "AIProvider", "OpenAIProvider", "BedrockProvider"]
