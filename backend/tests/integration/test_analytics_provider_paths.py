"""Integration-style tests for analytics provider routing paths.

These tests verify that the orchestrator chooses the right analytics execution
path for OpenAI vs Ollama modes and returns stable fixture payloads.
"""

from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace

import pytest

if "agents" not in sys.modules:
    def _identity_tool(func=None, **kwargs):
        if func is None:
            def _decorator(inner):
                return inner
            return _decorator
        return func

    def _tool_namespace(name, description, tools):
        return tools

    class _DummyRunner:
        @staticmethod
        async def run(*args, **kwargs):
            return SimpleNamespace(final_output={})

    class _DummyAgent:
        def __init__(self, *args, **kwargs):
            self.name = kwargs.get("name", "dummy-agent")

    class _ToolOutputGuardrail:
        def __class_getitem__(cls, item):
            return cls

    class _ToolGuardrailFunctionOutput:
        @staticmethod
        def reject_content(*args, **kwargs):
            return object()

        @staticmethod
        def allow(*args, **kwargs):
            return object()

    agents_module = types.ModuleType("agents")
    agents_module.Agent = _DummyAgent
    agents_module.Runner = _DummyRunner
    agents_module.set_default_openai_key = lambda *args, **kwargs: None
    agents_module.function_tool = _identity_tool
    agents_module.tool_namespace = _tool_namespace
    agents_module.ToolSearchTool = lambda *args, **kwargs: object()
    agents_module.ToolGuardrailFunctionOutput = _ToolGuardrailFunctionOutput
    agents_module.ToolOutputGuardrail = _ToolOutputGuardrail
    agents_module.tool_output_guardrail = lambda fn: fn
    agents_module.ModelSettings = lambda *args, **kwargs: object()

    extensions_module = types.ModuleType("agents.extensions")
    memory_module = types.ModuleType("agents.extensions.memory")
    memory_module.SQLAlchemySession = object

    sys.modules["agents"] = agents_module
    sys.modules["agents.extensions"] = extensions_module
    sys.modules["agents.extensions.memory"] = memory_module

    # Backward-compatible namespace object for any direct attribute lookups.
    sys.modules["agents_namespace_fallback"] = SimpleNamespace(
        Agent=_DummyAgent,
        Runner=_DummyRunner,
        set_default_openai_key=lambda *args, **kwargs: None,
        function_tool=_identity_tool,
        tool_namespace=_tool_namespace,
        ToolSearchTool=lambda *args, **kwargs: object(),
        ToolGuardrailFunctionOutput=_ToolGuardrailFunctionOutput,
        ToolOutputGuardrail=_ToolOutputGuardrail,
        tool_output_guardrail=lambda fn: fn,
        ModelSettings=lambda *args, **kwargs: object(),
    )

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

    ingestion_agent_module.ingestion_openai_agent = object()
    ingestion_agent_module.IngestionAgent = _DummyIngestionAgent
    sys.modules["app.agents.ingestion_agent"] = ingestion_agent_module

if "app.agents.tagging_agent" not in sys.modules:
    tagging_agent_module = types.ModuleType("app.agents.tagging_agent")
    tagging_agent_module.tagging_agent = object()
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

    async def _fake_runner_run(agent, message, session=None):
        return SimpleNamespace(final_output=OPENAI_ANALYTICS_FIXTURE)

    class _RunnerStub:
        @staticmethod
        async def run(agent, message, session=None):
            return await _fake_runner_run(agent, message, session=session)

    monkeypatch.setattr(orchestrator_module, "handle_intent", _fake_handle_intent)
    monkeypatch.setattr(orchestrator_module.settings, "ai_provider", "openai")
    monkeypatch.setattr(orchestrator_module, "set_default_openai_key", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "get_agent_sqlalchemy_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "analytics_openai_agent", SimpleNamespace(name="analytics-agent"))
    monkeypatch.setattr(orchestrator_module, "Runner", _RunnerStub)

    orchestrator = orchestrator_module.AgentOrchestrator()
    result = await orchestrator.execute({"message": "What is our Instagram reach this week?"})

    assert result == OPENAI_ANALYTICS_FIXTURE


@pytest.mark.asyncio
async def test_orchestrator_uses_ollama_provider_service_for_analytics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_handle_intent(message: str, context: dict | None = None) -> str:
        return "query_metrics"

    async def _fake_execute_analytics_with_provider(message: str):
        return OLLAMA_ANALYTICS_FIXTURE

    monkeypatch.setattr(orchestrator_module, "handle_intent", _fake_handle_intent)
    monkeypatch.setattr(orchestrator_module.settings, "ai_provider", "ollama")
    monkeypatch.setattr(orchestrator_module, "set_default_openai_key", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        orchestrator_module,
        "execute_analytics_with_provider",
        _fake_execute_analytics_with_provider,
    )

    orchestrator = orchestrator_module.AgentOrchestrator()
    result = await orchestrator.execute({"message": "What is our Instagram reach this week?"})

    assert result == OLLAMA_ANALYTICS_FIXTURE
