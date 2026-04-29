"""OpenAI provider adapter (v1).

Provides a small factory `get_provider` that constructs and returns a
configured Strands `OpenAIResponsesModel` instance. Configuration can be
passed via the `config` dict so callers (or DI/factory code) can control
`model_id`, `client_args`, `params`, and `stateful`.

If the `strands` package is not installed this module raises a helpful
ImportError explaining how to install the optional dependency.
"""
from app.logging import get_logger
from app.config import settings, AISettings

logger = get_logger(__name__)

def get_model(config: AISettings):
    """Create and return a configured Strands `LitertResponsesModel`.
    Args:
        config: Optional dict with keys:
            - model_id: str
            - client_args: dict
            - params: dict
            - stateful: bool

    Returns:
        An instance of `strands.models.litellm.LiteLLMModel`.

    Raises:
        ImportError: If the Strands LiteLLMModel is not available.
    """
    model_id = config.model_name or settings.main_model
    base_url = config.base_url or settings.main_model_base_url
    api_key = config.api_key
    params = config.params

    try:
        from strands.models.litellm import LiteLLMModel  
    except Exception as e:
        msg = (
            "strands-agents[litellm] (and its dependencies) are required to use the v1 LiteLLM provider. "
            "Install with: pip install 'strands-agents[litellm]' strands-agents-tools"
        )
        logger.error("failed to import LiteLLMModel", error=str(e))
        raise ImportError(msg) from e

    model = LiteLLMModel(
        client_args={
            "api_key": api_key,
        },
        # **model_config
        model_id=model_id,
        params=params or None,
    )

    logger.info("LiteLLMModel created", model_id=model_id)
    return model
