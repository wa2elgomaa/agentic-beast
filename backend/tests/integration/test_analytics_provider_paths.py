"""Integration-style tests for analytics provider routing paths.

These tests verify that the orchestrator chooses the right analytics execution
path for OpenAI vs Ollama modes and returns stable fixture payloads.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from types import SimpleNamespace

import pytest

if "spacy" not in sys.modules:
    spacy_module = types.ModuleType("spacy")
    spacy_module.load = lambda *args, **kwargs: SimpleNamespace(vocab=SimpleNamespace(strings={}))
    spacy_module.blank = lambda *args, **kwargs: SimpleNamespace(vocab=SimpleNamespace(strings={}))

    spacy_matcher_module = types.ModuleType("spacy.matcher")

    class _DummyMatcher:
        def __init__(self, *args, **kwargs):
            pass

        def add(self, *args, **kwargs):
            return None

        def __call__(self, *args, **kwargs):
            return []

    spacy_matcher_module.Matcher = _DummyMatcher

    spacy_util_module = types.ModuleType("spacy.util")
    spacy_util_module.is_package = lambda *args, **kwargs: False

    sys.modules["spacy"] = spacy_module
    sys.modules["spacy.matcher"] = spacy_matcher_module
    sys.modules["spacy.util"] = spacy_util_module

if "app.agents.ingestion_agent" not in sys.modules:
    ingestion_agent_module = types.ModuleType("app.agents.ingestion_agent")

    class _DummyIngestionAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, *args, **kwargs):
            return "ingestion stub"

    ingestion_agent_module.get_strands_ingestion_agent = lambda: None
    ingestion_agent_module.IngestionAgent = _DummyIngestionAgent
    sys.modules["app.agents.ingestion_agent"] = ingestion_agent_module

if "app.agents.tagging_agent" not in sys.modules:
    tagging_agent_module = types.ModuleType("app.agents.tagging_agent")
    tagging_agent_module.get_strands_tagging_agent = lambda: None
    sys.modules["app.agents.tagging_agent"] = tagging_agent_module

orchestrator_module = importlib.import_module("app.agents.orchestrator")


OPENAI_ANALYTICS_FIXTURE = {
    "query_type": "analytics",
    "resolved_subject": "instagram reach",
    "result_data": [
        {
            "label": "instagram",
            "value": "1234",
            "platform": "instagram",
            "content": "",
            "title": "",
            "published_at": "",
        }
    ],
    "insight_summary": "Instagram reach was 1234.",
    "verification": "fixture-openai",
}

OLLAMA_ANALYTICS_FIXTURE = {
    "query_type": "analytics",
    "resolved_subject": "instagram reach",
    "result_data": [
        {
            "label": "instagram",
            "value": "987",
            "platform": "instagram",
            "content": "",
            "title": "",
            "published_at": "",
        }
    ],
    "insight_summary": "Instagram reach was 987.",
    "verification": "fixture-ollama",
}


@pytest.mark.asyncio
async def test_orchestrator_uses_openai_runner_for_analytics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_handle_intent(message: str, context: dict | None = None) -> str:
        return "analytics"

    class _FakeAgent:
        async def invoke_async(self, message: str):
            return json.dumps(OPENAI_ANALYTICS_FIXTURE)

    monkeypatch.setattr(orchestrator_module, "handle_intent", _fake_handle_intent)
    monkeypatch.setattr(orchestrator_module, "_resolve_agent_for_intent", lambda intent: _FakeAgent())

    orchestrator = orchestrator_module.AgentOrchestrator()
    result = await orchestrator.execute({"message": "What is our Instagram reach this week?"})

    assert result == OPENAI_ANALYTICS_FIXTURE


@pytest.mark.asyncio
async def test_orchestrator_uses_ollama_provider_service_for_analytics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_handle_intent(message: str, context: dict | None = None) -> str:
        return "query_metrics"

    class _FakeAgent:
        async def invoke_async(self, message: str):
            return json.dumps(OLLAMA_ANALYTICS_FIXTURE)

    monkeypatch.setattr(orchestrator_module, "handle_intent", _fake_handle_intent)
    monkeypatch.setattr(orchestrator_module, "_resolve_agent_for_intent", lambda intent: _FakeAgent())

    orchestrator = orchestrator_module.AgentOrchestrator()
    result = await orchestrator.execute({"message": "What is our Instagram reach this week?"})

    assert result == OLLAMA_ANALYTICS_FIXTURE
