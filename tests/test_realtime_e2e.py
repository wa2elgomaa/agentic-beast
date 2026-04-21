import json
import base64
import uuid

from fastapi.testclient import TestClient

from fastapi import FastAPI
from app.api import chat_realtime

# Create a lightweight FastAPI instance for this test that only includes the
# realtime chat router. Importing the full `app.main.app` triggers optional
# runtime dependencies (scheduler/apscheduler) that aren't available in the
# test environment.
app = FastAPI()
app.include_router(chat_realtime.router, prefix="/api/v1", tags=["chat-realtime"])


class FakeAuthService:
    def verify_token(self, token: str):
        # Accept any token and return a payload with a user id
        return {"sub": str(uuid.uuid4())}


class FakeUser:
    def __init__(self, id_str: str, is_active: bool = True):
        self.id = uuid.UUID(id_str)
        self.is_active = is_active


class FakeUserService:
    def __init__(self, session):
        pass

    async def get_user_by_id(self, user_id: str):
        return FakeUser(user_id)


class FakeRuntime:
    async def dependency_status(self):
        return {"provider": "fake", "enabled": True, "ready": True}

    async def create_session(self, user_id, conversation_id=None):
        return {"session_id": "fake-session-1234"}

    async def handle_event(self, session_id, event):
        # Emit a deterministic sequence: transcript -> assistant_text -> audio_start -> audio_chunk -> audio_end
        transcript = {"type": "transcript", "session_id": session_id, "message": "partial transcript", "data": {}}
        assistant_text = {"type": "assistant_text", "session_id": session_id, "message": "Hello from fake runtime", "data": {}}
        audio_start = {"type": "audio_start", "session_id": session_id, "data": {"sample_rate": 16000}}
        audio_chunk = {"type": "audio_chunk", "session_id": session_id, "data": {"chunk": base64.b64encode(b"\x01\x02\x03").decode("ascii")}}
        audio_end = {"type": "audio_end", "session_id": session_id, "data": {}}
        return [transcript, assistant_text, audio_start, audio_chunk, audio_end]

    async def close_session(self, session_id):
        return


def test_realtime_websocket_event_sequence(monkeypatch):
    # Monkeypatch authentication, user lookup, and runtime used by the websocket handler
    monkeypatch.setattr(chat_realtime, "get_auth_service", lambda: FakeAuthService())
    monkeypatch.setattr(chat_realtime, "UserService", FakeUserService)
    monkeypatch.setattr(chat_realtime, "get_polar_runtime_service", lambda: FakeRuntime())

    client = TestClient(app)

    # connect (token value doesn't matter because FakeAuthService accepts any token)
    with client.websocket_connect("/api/v1/chat/realtime/ws?token=any-token&conversation_id=test-conv") as ws:
        # First messages: session_ready, provider_status
        msg = ws.receive_json()
        assert msg["type"] == "session_ready"
        msg = ws.receive_json()
        assert msg["type"] == "provider_status"

        # Send a client audio event (small base64 payload)
        client_event = {"type": "audio", "audio": base64.b64encode(b"\x00\x01").decode("ascii")}
        ws.send_text(json.dumps(client_event))

        # Verify server responses arrive in expected order
        msg = ws.receive_json()
        assert msg["type"] == "transcript"
        msg = ws.receive_json()
        assert msg["type"] == "assistant_text"
        msg = ws.receive_json()
        assert msg["type"] == "audio_start"
        msg = ws.receive_json()
        assert msg["type"] == "audio_chunk"
        msg = ws.receive_json()
        assert msg["type"] == "audio_end"
