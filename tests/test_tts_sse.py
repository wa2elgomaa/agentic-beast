import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# Prevent heavy scheduler imports during test collection by stubbing the
# scheduler_service module before importing app.main
import sys
import types

fake_scheduler_mod = types.ModuleType("app.services.scheduler_service")
class DummyScheduler:
    @staticmethod
    async def start():
        return None

    @staticmethod
    async def shutdown():
        return None

fake_scheduler_mod.SchedulerService = DummyScheduler
sys.modules["app.services.scheduler_service"] = fake_scheduler_mod

from app.main import create_app


class MockChatService:
    def __init__(self, message):
        self._message = message

    async def get_message_by_id(self, message_id):
        return self._message
    
    async def get_conversation(self, conversation_id, user_id=None):
        # Return a dummy conversation object to satisfy access checks
        return SimpleNamespace(id=conversation_id, user_id=user_id)


def make_event(t, data=None, message=None):
    payload = {"type": t}
    if data is not None:
        payload["data"] = data
    if message is not None:
        payload["message"] = message
    return payload


def test_sse_stream_stored_chunks(monkeypatch):
    app = create_app()

    # Create a fake assistant message with stored tts chunks
    fake_chunks = ["ZmFrZV9kYXRh"]  # base64 placeholder
    message = SimpleNamespace(id="m1", role="assistant", content="Hello", operation_data={"tts": {"sample_rate": 16000, "chunks": fake_chunks}})

    mock_service = MockChatService(message)

    # Override dependencies: chat service and current user
    from app.api.chat import get_chat_service
    from app.api.users import get_current_user

    app.dependency_overrides[get_chat_service] = lambda: mock_service
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="dummy-user")

    client = TestClient(app)

    url = f"/api/v1/chat/conversations/00000000-0000-0000-0000-000000000000/messages/11111111-1111-1111-1111-111111111111/tts/stream"
    with client.stream("GET", url) as resp:
        assert resp.status_code == 200
        # collect SSE data lines
        data = b"".join(resp.iter_bytes())
        text = data.decode()
        # SSE events are 'data: <json>\n\n'
        assert "audio_start" in text
        assert "audio_chunk" in text
        assert "audio_end" in text


def test_sse_stream_on_demand(monkeypatch):
    app = create_app()

    # Create a fake assistant message without stored tts
    message = SimpleNamespace(id="m2", role="assistant", content="On demand text", operation_data=None)
    mock_service = MockChatService(message)

    from app.api.chat import get_chat_service
    from app.api.users import get_current_user
    app.dependency_overrides[get_chat_service] = lambda: mock_service
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="dummy-user")

    # Mock multimodal provider to yield events
    class FakeProvider:
        async def stream_tts(self, text):
            yield make_event("audio_start", {"sample_rate": 22050})
            yield make_event("audio_chunk", {"audio": "ZmFrZQ==", "index": 0})
            yield make_event("audio_end", {})

    monkeypatch.setattr("app.api.chat.get_ai_provider", lambda: FakeProvider(), raising=False)
    # Also patch factory import used in endpoint
    import app.providers.factory as pf

    monkeypatch.setattr(pf, "get_ai_provider", lambda options=None: FakeProvider())

    client = TestClient(app)
    url = f"/api/v1/chat/conversations/00000000-0000-0000-0000-000000000000/messages/22222222-2222-2222-2222-222222222222/tts/stream"
    with client.stream("GET", url) as resp:
        assert resp.status_code == 200
        data = b"".join(resp.iter_bytes())
        text = data.decode()
        assert "audio_start" in text
        assert "audio_chunk" in text
        assert "audio_end" in text
