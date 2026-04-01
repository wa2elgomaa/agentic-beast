import importlib.util
import pathlib

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
