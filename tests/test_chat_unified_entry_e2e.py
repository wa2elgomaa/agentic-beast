import sys
import types
import json
from types import SimpleNamespace
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

# Stub optional apscheduler modules so the app imports successfully in tests.
sys.modules.setdefault('apscheduler', types.ModuleType('apscheduler'))
sys.modules.setdefault('apscheduler.schedulers', types.ModuleType('apscheduler.schedulers'))
mod = types.ModuleType('apscheduler.schedulers.asyncio')
class AsyncIOScheduler:
    def __init__(self, *args, **kwargs):
        pass
    async def start(self):
        return None
    async def shutdown(self):
        return None
mod.AsyncIOScheduler = AsyncIOScheduler
sys.modules['apscheduler.schedulers.asyncio'] = mod
sys.modules.setdefault('apscheduler.triggers', types.ModuleType('apscheduler.triggers'))
cron_mod = types.ModuleType('apscheduler.triggers.cron')
class CronTrigger:
    def __init__(self, *args, **kwargs):
        pass
cron_mod.CronTrigger = CronTrigger
sys.modules['apscheduler.triggers.cron'] = cron_mod
date_mod = types.ModuleType('apscheduler.triggers.date')
class DateTrigger:
    def __init__(self, *args, **kwargs):
        pass
date_mod.DateTrigger = DateTrigger
sys.modules['apscheduler.triggers.date'] = date_mod

# Stub the app.services.scheduler_service module to avoid importing the real scheduler and its dependencies.
sched_mod = types.ModuleType('app.services.scheduler_service')
class SchedulerService:
    @staticmethod
    async def start():
        return None
    @staticmethod
    async def shutdown():
        return None
    @staticmethod
    async def schedule_task(*args, **kwargs):
        return None
sched_mod.SchedulerService = SchedulerService
sys.modules['app.services.scheduler_service'] = sched_mod

from app.main import app


class StubChatService:
    def __init__(self):
        now = datetime.utcnow()
        self._conv = SimpleNamespace(id=uuid4())
        self._user_msg = SimpleNamespace(id=uuid4(), role="user", content="Hi", created_at=now)
        # assistant content as structured JSON string to exercise normalization
        self._assistant_msg = SimpleNamespace(
            id=uuid4(), role="assistant", content=json.dumps({"note": "ok"}), created_at=now
        )

    async def handle_user_message(self, message_content, conversation_id=None, user_id=None):
        return self._conv, self._user_msg, self._assistant_msg

    async def handle_media_message(self, *args, **kwargs):
        return self._conv, self._user_msg, self._assistant_msg

    async def format_message_response(self, msg):
        # Return the minimal dict matching MessageResponse shape
        content = msg.content
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
            content = parsed
        except Exception:
            content = content

        return {
            "id": str(msg.id),
            "role": msg.role,
            "content": content,
            "created_at": msg.created_at.isoformat(),
        }


class DummyUser:
    def __init__(self):
        self.id = uuid4()
        self.username = "wael"
        self.is_active = True
        self.is_admin = True


@pytest.fixture(autouse=True)
def override_dependencies():
    # Override auth and chat_service dependencies to return stubs
    from app.api.chat import get_chat_service
    from app.api.users import get_current_user

    def _get_stub_chat_service():
        return StubChatService()

    def _get_dummy_user():
        return DummyUser()

    app.dependency_overrides[get_chat_service] = lambda: _get_stub_chat_service()
    app.dependency_overrides[get_current_user] = lambda: _get_dummy_user()

    yield

    app.dependency_overrides.clear()


def test_text_chat_unified_entry():
    client = TestClient(app)

    payload = {"message": "Hello from test"}
    resp = client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "success"
    assert "message" in data
    assert data["message"]["content"]["note"] == "ok"


def test_media_chat_unified_entry():
    client = TestClient(app)

    # small dummy base64 for test; MediaProcessingService is stubbed by chat_service
    payload = {"audio": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsA", "audio_format": "wav"}
    resp = client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "success"
    assert data["message"]["content"]["note"] == "ok"
