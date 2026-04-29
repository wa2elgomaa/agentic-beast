"""Response Agent — thin passthrough that normalises sub-agent output.

The previous implementation made a second LLM call here which caused
structured ``response_json`` data to be discarded.  This version is a
pure-Python formatter: no LLM call, no latency, no data loss.

Kept for backward compatibility with any code that imports ``ResponseAgent``
or ``get_agent``.  The orchestrator no longer calls this.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel as PydanticBaseModel, Field

from app.logging import get_logger

logger = get_logger(__name__)


class ResponseAgentSchema(PydanticBaseModel):
    response_text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResponseAgent:
    """No-op passthrough — returns the input text unchanged."""

    async def execute(self, raw_input: str, original_context: Dict) -> ResponseAgentSchema:
        return ResponseAgentSchema(response_text=raw_input, metadata={})


def get_agent() -> ResponseAgent:
    return ResponseAgent()


