import sys
import types
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# Provide a minimal `apscheduler` shim so importing `app.main` during tests
# does not require the actual dependency to be installed.
aps_mod = types.ModuleType("apscheduler")
aps_schedulers = types.ModuleType("apscheduler.schedulers")
aps_asyncio = types.ModuleType("apscheduler.schedulers.asyncio")
class _StubScheduler:
    def start(self):
        pass
    def shutdown(self):
        pass
aps_asyncio.AsyncIOScheduler = _StubScheduler
sys.modules["apscheduler"] = aps_mod
sys.modules["apscheduler.schedulers"] = aps_schedulers
sys.modules["apscheduler.schedulers.asyncio"] = aps_asyncio
# Minimal trigger shim
aps_triggers = types.ModuleType("apscheduler.triggers")
aps_triggers_cron = types.ModuleType("apscheduler.triggers.cron")
class CronTrigger:
    def __init__(self, *args, **kwargs):
        pass
aps_triggers_cron.CronTrigger = CronTrigger
sys.modules["apscheduler.triggers"] = aps_triggers
sys.modules["apscheduler.triggers.cron"] = aps_triggers_cron
aps_triggers_date = types.ModuleType("apscheduler.triggers.date")
class DateTrigger:
    def __init__(self, *args, **kwargs):
        pass
aps_triggers_date.DateTrigger = DateTrigger
sys.modules["apscheduler.triggers.date"] = aps_triggers_date

# Provide a stub for app.services.scheduler_service to avoid complex scheduler imports
svc_mod = types.ModuleType("app.services.scheduler_service")
class _SvcStub:
    @staticmethod
    def start():
        pass
    @staticmethod
    def shutdown():
        pass
svc_mod.SchedulerService = _SvcStub
sys.modules["app.services.scheduler_service"] = svc_mod

from app.main import app as _app


class FakeChatService:
    def __init__(self):
        self.last_message = None

    async def handle_user_message(self, message_content, conversation_id, user_id):
        conv = SimpleNamespace(id=uuid.uuid4())
        user_msg = SimpleNamespace(id=uuid.uuid4(), role="user", content=message_content)
        assistant_msg = SimpleNamespace(id=uuid.uuid4(), role="assistant", content=f"Echo: {message_content}")
        return conv, user_msg, assistant_msg

    async def handle_media_message(self, **kwargs):
        conv = SimpleNamespace(id=uuid.uuid4())
        user_msg = SimpleNamespace(id=uuid.uuid4(), role="user", content="[media]")
        assistant_msg = SimpleNamespace(id=uuid.uuid4(), role="assistant", content="Media response")
        return conv, user_msg, assistant_msg

    async def format_message_response(self, msg):
        from datetime import datetime
        return {"id": str(getattr(msg, "id", uuid.uuid4())), "role": getattr(msg, "role", "assistant"), "content": getattr(msg, "content", ""), "created_at": datetime.utcnow().isoformat()}


class FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.is_active = True


def test_chat_endpoint_inprocess(monkeypatch):
    # Override dependencies
    client = TestClient(_app)

    fake_service = FakeChatService()
    from app.api.chat import get_chat_service
    from app.api.auth_apikey import get_authenticated_user

    monkeypatch.setattr(_app, "dependency_overrides", {})
    _app.dependency_overrides[get_chat_service] = lambda: fake_service
    _app.dependency_overrides[get_authenticated_user] = lambda: FakeUser()

    resp = client.post("/api/v1/chat", json={"message": "Hello world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "success"
    assert "conversation_id" in data
    assert data.get("message") and data.get("user_message")
