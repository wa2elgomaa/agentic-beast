"""AWS Bedrock provider implementation."""

import json
from typing import List, Optional

import boto3

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider, CompletionResponse, Message

logger = get_logger(__name__)


class BedrockProvider(AIProvider):
    """AWS Bedrock AI provider implementation."""

    def __init__(self):
        """Initialize Bedrock provider."""
        super().__init__(settings.bedrock_model_id)
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        logger.info("Bedrock provider initialized", model=self.model)

    async def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        """Generate a completion using AWS Bedrock.

        Args:
            messages: List of messages in the conversation.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            Completion response.
        """
        try:
            # Prepare messages for Bedrock Claude model
            messages_list = [{"role": m.role, "content": m.content} for m in messages]

            # Build request body for Claude model
            body = {
                "messages": messages_list,
                "max_tokens": max_tokens or 1024,
                "temperature": temperature,
                **(kwargs or {}),
            }

            response = self.client.invoke_model(
                modelId=self.model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )

            response_body = json.loads(response["body"].read().decode())

            # Extract content from Claude response
            content = response_body["content"][0]["text"]

            return CompletionResponse(
                content=content,
                model=self.model,
                stop_reason=response_body.get("stop_reason"),
                usage=response_body.get("usage"),
            )

        except Exception as e:
            logger.error("Bedrock completion error", error=str(e))
            raise

    async def embed(self, text: str) -> List[float]:
        """Generate embeddings using AWS Bedrock.

        Note: Not all Bedrock models support embeddings.
        This is a placeholder implementation.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector.
        """
        logger.warning(
            "Bedrock embedding not implemented. Using placeholder.",
            text_length=len(text),
        )
        # Return a placeholder embedding
        # In production, use a dedicated embedding model from Bedrock
        return [0.0] * 384  # all-MiniLM-L6-v2 dimension
