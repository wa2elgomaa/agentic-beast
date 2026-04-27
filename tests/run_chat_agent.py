import sys
import os

from strands.models.openai import OpenAIModel
from strands.agent import Agent

from app.config.config import settings


def main():
    # Read OpenAI API key from env, then from project settings (backend/.env)
    openai_key = (
        "sk----"
    )

    if not openai_key:
        print("Error: no OpenAI API key found. Set OPENAI_API_KEY or configure main_api_key in backend/.env and retry.")
        print("Example (bash): export OPENAI_API_KEY='sk-...'; PYTHONPATH=backend/src python tests/run_chat_agent.py")
        sys.exit(1)

    model_id = os.environ.get("OPENAI_MODEL_ID") or "gpt-4o-mini"

    model = OpenAIModel(
        client_args={"api_key": openai_key},
        model_id=model_id,
        # params={"stream": False},
    )

    agent = Agent(model=model)

    # Simple prompt call for smoke-testing
    response = agent("Tell me a story")
    print("RESPONSE:", response)


if __name__ == '__main__':
    main()