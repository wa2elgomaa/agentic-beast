import pytest

from app.config.registry import initialize_registries
from app.agents.autonomous_router import route_analytics_query


@pytest.fixture(scope="module", autouse=True)
def _init_registries() -> None:
    initialize_registries(config_dir="config")


@pytest.mark.asyncio
async def test_router_uses_code_interpreter_when_confident(monkeypatch) -> None:
    async def _fake_json(*args, **kwargs):  # noqa: ANN002, ANN003
        return {
            "target": "code_interpreter",
            "confidence": 0.91,
            "reasoning": "follow-up with prior sql",
            "mode": "follow_up",
        }

    monkeypatch.setattr("app.agents.autonomous_router.generate_json_object", _fake_json)

    result = await route_analytics_query(
        message="Break them down by platform",
        conversation_history=[{"role": "assistant", "prior_sql": "SELECT ..."}],
    )

    assert result["target"] == "code_interpreter"
    assert result["mode"] == "follow_up"


@pytest.mark.asyncio
async def test_router_falls_back_to_sql_on_low_confidence(monkeypatch) -> None:
    async def _fake_json(*args, **kwargs):  # noqa: ANN002, ANN003
        return {
            "target": "code_interpreter",
            "confidence": 0.2,
            "reasoning": "uncertain",
            "mode": "follow_up",
        }

    monkeypatch.setattr("app.agents.autonomous_router.generate_json_object", _fake_json)

    result = await route_analytics_query(
        message="compare that to last result",
        conversation_history=[{"role": "assistant", "prior_sql": "SELECT ..."}],
    )

    assert result["target"] == "sql_analytics"
    assert "low_confidence" in result["reasoning"]


@pytest.mark.asyncio
async def test_router_falls_back_on_invalid_target(monkeypatch) -> None:
    async def _fake_json(*args, **kwargs):  # noqa: ANN002, ANN003
        return {
            "target": "invalid_pipeline",
            "confidence": 0.99,
            "reasoning": "bad output",
            "mode": "initial",
        }

    monkeypatch.setattr("app.agents.autonomous_router.generate_json_object", _fake_json)

    result = await route_analytics_query(
        message="show top videos",
        conversation_history=None,
    )

    assert result["target"] == "sql_analytics"
    assert result["confidence"] == 0.0
