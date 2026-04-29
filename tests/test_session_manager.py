import pytest

from app.services.session_manager import SessionManager


@pytest.mark.asyncio
async def test_queue_policy_cancel_oldest():
    mgr = SessionManager(max_concurrent=1)
    rec1 = await mgr.create_session("s1")
    assert await mgr.get_session("s1") is not None

    # Creating a second session with cancel_oldest should replace the first
    rec2 = await mgr.create_session("s2", queue_policy="cancel_oldest")
    active = await mgr.list_active()
    ids = [r.session_id for r in active]
    assert "s2" in ids and "s1" not in ids


@pytest.mark.asyncio
async def test_queue_policy_queue_and_promotion():
    mgr = SessionManager(max_concurrent=1)
    await mgr.create_session("s1")
    await mgr.create_session("s2", queue_policy="queue")

    # s2 should be queued
    assert len(mgr._queue) == 1 and mgr._queue[0].session_id == "s2"

    # Closing s1 should promote s2 to active
    await mgr.close_session("s1")
    active = await mgr.list_active()
    assert any(r.session_id == "s2" for r in active)
