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
    """Create and return a configured Strands `OpenAIResponsesModel`.
    Args:
        config: Optional dict with keys:
            - model_id: str
            - client_args: dict
            - params: dict
            - stateful: bool

    Returns:
        An instance of `strands.models.openai_responses.OpenAIResponsesModel`.

    Raises:
        ImportError: If the Strands OpenAIResponsesModel is not available.
    """
    model_id = config.model_name or settings.main_model
    api_key = config.api_key
    base_url = config.base_url
    params = config.params or {}

    try:
        from strands.models.openai import OpenAIModel  
    except Exception as e:
        msg = (
            "strands-agents[openai] (and its dependencies) are required to use the v1 OpenAI provider. "
            "Install with: pip install 'strands-agents[openai]' strands-agents-tools"
        )
        logger.error("failed to import OpenAIModel", error=str(e))
        raise ImportError(msg) from e

    # Only pass non-empty values so the SDK can fall back to its own env-var
    # defaults (OPENAI_API_KEY, OPENAI_BASE_URL).  Passing an empty string for
    # either causes the OpenAI client to use "" as-is, leading to a protocol
    # error or authentication failure.
    client_args: dict = {}
    if api_key:
        client_args["api_key"] = api_key
    if base_url:
        client_args["base_url"] = base_url

    model = OpenAIModel(
        model_id=model_id,
        client_args=client_args,
        params=params,
    )

    logger.info("OpenAIModel created", model_id=model_id)
    return model
