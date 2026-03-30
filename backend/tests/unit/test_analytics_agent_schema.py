import importlib.util
import pathlib
import sys
import types

if "agents" not in sys.modules:
    def _identity_tool(func=None, **kwargs):
        if func is None:
            def _decorator(inner):
                return inner
            return _decorator
        return func

    def _tool_namespace(name, description, tools):
        return tools

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
    agents_module.CodeInterpreterTool = lambda *args, **kwargs: object()
    agents_module.Agent = lambda *args, **kwargs: object()
    agents_module.ModelSettings = lambda *args, **kwargs: object()
    agents_module.TResponseInputItem = object
    agents_module.Runner = object
    agents_module.RunConfig = object
    agents_module.trace = lambda *args, **kwargs: None
    agents_module.set_default_openai_key = lambda *args, **kwargs: None
    agents_module.function_tool = _identity_tool
    agents_module.tool_namespace = _tool_namespace
    agents_module.ToolSearchTool = lambda *args, **kwargs: object()
    agents_module.ToolOutputGuardrail = _ToolOutputGuardrail
    agents_module.ToolGuardrailFunctionOutput = _ToolGuardrailFunctionOutput
    agents_module.tool_output_guardrail = lambda fn: fn

    sys.modules["agents"] = agents_module

    extensions_module = types.ModuleType("agents.extensions")
    memory_module = types.ModuleType("agents.extensions.memory")
    memory_module.SQLAlchemySession = object
    sys.modules["agents.extensions"] = extensions_module
    sys.modules["agents.extensions.memory"] = memory_module

MODULE_PATH = pathlib.Path(__file__).resolve().parents[2] / "src" / "app" / "agents" / "analytics_agent.py"
spec = importlib.util.spec_from_file_location("analytics_agent_for_test", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
AnalyticsAgentSchema__ResultDataItem = module.AnalyticsAgentSchema__ResultDataItem


def test_result_item_validators_sanitize_multiline_fields() -> None:
    item = AnalyticsAgentSchema__ResultDataItem(
        label="instagram_reach",
        value="0",
        platform="linkedin",
        content='Line 1\nLine 2 with "quoted" text',
        title='Title\nwith break',
    )

    assert "\n" not in item.content
    assert "\n" not in item.title
    assert item.content.startswith("Line 1 Line 2")


def test_result_item_validators_cap_lengths() -> None:
    item = AnalyticsAgentSchema__ResultDataItem(
        label="instagram_reach",
        value="12",
        platform="instagram",
        content="c" * 800,
        title="t" * 500,
    )

    assert len(item.content) <= 480
    assert len(item.title) <= 240
