import pytest

from app.config.registry import initialize_registries
from app.utilities.intent_classifier import IntentClassifier


@pytest.fixture(scope="module", autouse=True)
def _init_registries() -> None:
    initialize_registries(config_dir="config")


@pytest.mark.asyncio
async def test_alias_intent_maps_to_legacy_label(monkeypatch) -> None:
    async def _fake_json(*args, **kwargs):  # noqa: ANN002, ANN003
        return {
            "intent": "tagging",
            "confidence": 0.95,
            "reasoning": "matched tagging intent",
        }

    monkeypatch.setattr("app.utilities.intent_classifier.generate_json_object", _fake_json)

    result = await IntentClassifier.classify_detailed("suggest tags for this article")

    assert result["raw_intent"] == "tagging"
    assert result["intent"] == "tag_suggestions"
    assert result["confidence"] == 0.95


@pytest.mark.asyncio
async def test_low_confidence_uses_fallback(monkeypatch) -> None:
    async def _fake_json(*args, **kwargs):  # noqa: ANN002, ANN003
        return {
            "intent": "analytics",
            "confidence": 0.2,
            "reasoning": "weak signal",
        }

    monkeypatch.setattr("app.utilities.intent_classifier.generate_json_object", _fake_json)

    result = await IntentClassifier.classify_detailed("can you help me")

    # intents.yaml fallback_intent is "general", which maps to legacy "unknown"
    assert result["intent"] == "unknown"
    assert result["raw_intent"] == "analytics"


@pytest.mark.asyncio
async def test_invalid_intent_uses_fallback(monkeypatch) -> None:
    async def _fake_json(*args, **kwargs):  # noqa: ANN002, ANN003
        return {
            "intent": "not_a_real_intent",
            "confidence": 0.99,
            "reasoning": "bad label",
        }

    monkeypatch.setattr("app.utilities.intent_classifier.generate_json_object", _fake_json)

    result = await IntentClassifier.classify_detailed("random input")

    assert result["intent"] == "unknown"
    assert result["raw_intent"] == "not_a_real_intent"
