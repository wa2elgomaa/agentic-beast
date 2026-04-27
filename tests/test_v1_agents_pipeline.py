import pytest
import asyncio

from uuid import uuid4

from app.agents.v1.classify_agent import ClassifyAgent
from app.agents.v1.analytics_agent import AnalyticsAgent
from app.agents.v1.sql_agent import SQLAgent


class MockProviderFactory:
    def __init__(self, responses):
        # responses: list of objects to return in order for successive generate() calls
        self._responses = list(responses)

    async def generate(self, *args, **kwargs):
        if not self._responses:
            return {"text": ""}
        resp = self._responses.pop(0)
        # if resp is a dict return as-is, otherwise wrap in dict
        return resp


@pytest.mark.asyncio
async def test_text_pipeline_end_to_end():
    user_id = str(uuid4())
    message = "Give me an analytics report of user signups last month"

    # Prepare mock responses: classify -> analytics -> sql interpreter
    classify_resp = {"text": '{"intent": "analytics"}'}
    analytics_resp = {"text": '```sql\nSELECT user_id, COUNT(*) FROM signups WHERE created_at > \"2024-01-01\";\n```'}
    sql_resp = {"text": 'SELECT user_id, COUNT(*) FROM signups WHERE created_at > \"2024-01-01\";'}

    mock_factory = MockProviderFactory([classify_resp, analytics_resp, sql_resp])

    classify_agent = ClassifyAgent(provider_factory=mock_factory)
    analytics_agent = AnalyticsAgent(provider_factory=mock_factory)
    sql_agent = SQLInterpreterAgent(provider_factory=mock_factory)

    # Run classifier
    cls = await classify_agent.classify(user_id=user_id, message=message, context={})
    assert cls.get("intent") == "analytics"

    # Run analytics agent
    ctx = {"message": message}
    analytics_result = await analytics_agent.handle(user_id=user_id, context=ctx)
    assert "generated_sql" in analytics_result
    assert "SELECT" in analytics_result["generated_sql"].upper()

    # Run SQL interpreter agent
    sql_result = await sql_agent.interpret(user_id=user_id, message=message, context={})
    assert "sql" in sql_result
    assert sql_result["sql"].strip().upper().startswith("SELECT")


@pytest.mark.asyncio
async def test_audio_pipeline_end_to_end():
    user_id = str(uuid4())
    # Simulated transcript from audio
    transcript = "How many users signed up in January?"

    # Prepare mock responses as before
    classify_resp = {"text": '{"intent": "analytics"}'}
    analytics_resp = {"text": '```sql\nSELECT COUNT(*) FROM signups WHERE created_at >= \"2024-01-01\" AND created_at < \"2024-02-01\";\n```'}
    sql_resp = {"text": 'SELECT COUNT(*) FROM signups WHERE created_at >= \"2024-01-01\" AND created_at < \"2024-02-01\";'}

    mock_factory = MockProviderFactory([classify_resp, analytics_resp, sql_resp])

    classify_agent = ClassifyAgent(provider_factory=mock_factory)
    analytics_agent = AnalyticsAgent(provider_factory=mock_factory)
    sql_agent = SQLInterpreterAgent(provider_factory=mock_factory)

    # Simulate media processing: we have a transcript; reuse text pipeline
    cls = await classify_agent.classify(user_id=user_id, message=transcript, context={})
    assert cls.get("intent") == "analytics"

    analytics_result = await analytics_agent.handle(user_id=user_id, context={"message": transcript})
    assert "generated_sql" in analytics_result

    sql_result = await sql_agent.interpret(user_id=user_id, message=transcript, context={})
    assert sql_result.get("sql")
