import pytest

from app.agents.v1.classify_agent import ClassifyAgent
from app.agents.v1.analytics_agent import AnalyticsAgent


@pytest.mark.asyncio
async def test_agents_pipeline_e2e(monkeypatch):
    """End-to-end pipeline: message -> classify -> analytics -> SQL generation."""

    class FakeProviderFactory:
        async def generate(self, prompt, user_id=None, context=None, provider_name=None, options=None, **kwargs):
            txt = (prompt or "")
            # ClassifyAgent calls generate with max_tokens=64 and temperature=0.0
            if kwargs.get("max_tokens") == 64:
                # Return a JSON intent for classification
                return {"text": '{"intent":"analytics"}'}

            # AnalyticsAgent calls with max_tokens=512; return a SQL string
            if "revenue" in txt.lower():
                return {"text": "SELECT date, SUM(revenue) AS revenue FROM sales WHERE date >= '2026-03-01' GROUP BY date"}

            return {"text": ""}

    factory = FakeProviderFactory()

    # Replace module-level `settings` objects used by agents with a simple stub
    from types import SimpleNamespace
    import app.agents.v1.classify_agent as classify_mod
    import app.agents.v1.analytics_agent as analytics_mod

    stub_settings = SimpleNamespace(main_llm_provider="litert", main_model="", main_api_key="", sql_model="")
    monkeypatch.setattr(classify_mod, "settings", stub_settings)
    monkeypatch.setattr(analytics_mod, "settings", stub_settings)

    classify_agent = ClassifyAgent(provider_factory=factory)
    analytics_agent = AnalyticsAgent(provider_factory=factory)

    intent_res = await classify_agent.classify(user_id="test-user", message="Show revenue for last month")
    assert intent_res.get("intent") == "analytics"

    analytics_res = await analytics_agent.handle(user_id="test-user", context={"message": "Show revenue for last month"})
    assert analytics_res.get("intent") == "analytics"
    assert "SELECT" in analytics_res.get("generated_sql", "").upper()
