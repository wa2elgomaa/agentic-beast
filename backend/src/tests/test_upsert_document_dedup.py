"""Integration tests for _upsert_document deduplication logic.

Tests Pass 1 (exact match via identifier_column -> apply subtract strategy)
against a real database.  Run from backend/src:

    pytest tests/test_upsert_document_dedup.py -v
"""

import uuid
from datetime import time

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.schemas.document import Document
from app.schemas.ingestion_task import IngestionTask, TaskSchemaMapping
from app.services.ingestion_service import IngestionService

# ---------------------------------------------------------------------------
# Shared dedup config matching the production schema mapping
# ---------------------------------------------------------------------------
DEDUP_CONFIG = {
    "is_metric": {
        "labels": False,
        "paid_reach": True,
        "engagements": True,
        "total_reach": True,
        "video_views": True,
        "total_shares": True,
        "organic_reach": True,
        "total_comments": True,
        "completion_rate": True,
        "total_reactions": True,
        "paid_impressions": True,
        "video_length_sec": True,
        "total_impressions": True,
        "total_interactions": True,
        "organic_impressions": True,
        "organic_interactions": True,
        "avg_video_view_time_sec": True,
        "total_video_view_time_sec": True,
    },
    "default_strategy": "subtract",
    "field_strategies": {},
}

TEST_SHEET_PREFIX = "TEST_DEDUP_SHEET__"
DEDUP_TASK_NAME_PREFIX = "TEST_DEDUP_TASK__"


def _session_factory() -> async_sessionmaker:
    """NullPool engine: no connection is cached between event loops."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


def _row(content_id: str, video_views: int, sheet_name: str, row_number: int = 1) -> dict:
    return {
        "sheet_name": sheet_name,
        "row_number": row_number,
        "text": f"Test content {content_id}",
        "content_id": content_id,
        "platform": "instagram",
        "video_views": video_views,
        "total_reactions": 10,
        "total_comments": 5,
        "total_shares": 3,
        "is_current": True,
        "reported_time": time(9, 0, 0),
        "beast_uuid": uuid.uuid4(),
    }


@pytest_asyncio.fixture
async def dedup_task_id():
    """Create a throw-away IngestionTask + TaskSchemaMapping with DEDUP_CONFIG.

    Yields the task UUID for _upsert_document(task_id=...) calls.
    _get_dedup_config(task_id) will load DEDUP_CONFIG from this mapping.
    """
    tid = uuid.uuid4()
    sf = _session_factory()
    async with sf() as db:
        task = IngestionTask(
            id=tid,
            name=f"{DEDUP_TASK_NAME_PREFIX}{tid}",
            adaptor_type="manual",
            schedule_type="none",
        )
        db.add(task)
        await db.flush()

        mapping = TaskSchemaMapping(
            id=uuid.uuid4(),
            task_id=tid,
            source_columns=list(DEDUP_CONFIG["is_metric"].keys()),
            field_mappings={},
            identifier_column="content_id",
            dedup_config=DEDUP_CONFIG,
        )
        db.add(mapping)
        await db.commit()

    yield tid

    sf2 = _session_factory()
    async with sf2() as db:
        await db.execute(delete(TaskSchemaMapping).where(TaskSchemaMapping.task_id == tid))
        await db.execute(delete(IngestionTask).where(IngestionTask.id == tid))
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    sf = _session_factory()
    async with sf() as db:
        await db.execute(
            delete(Document).where(Document.sheet_name.like(f"{TEST_SHEET_PREFIX}%"))
        )
        await db.commit()
    yield
    sf2 = _session_factory()
    async with sf2() as db:
        await db.execute(
            delete(Document).where(Document.sheet_name.like(f"{TEST_SHEET_PREFIX}%"))
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Test 1 – same content_id, same value  =>  delta == 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_subtract_delta_same_value(dedup_task_id):
    content_id = "TEST_CONTENT_SAME_001"
    sheet1 = f"{TEST_SHEET_PREFIX}s1"
    sheet2 = f"{TEST_SHEET_PREFIX}s2"

    async with _session_factory()() as db:
        svc = IngestionService(db)

        r1 = await svc._upsert_document(
            _row(content_id, 32519, sheet1),
            identifier_column="content_id",
            task_id=dedup_task_id,
        )
        await db.commit()
        assert r1 == "inserted", f"Email 1 should be 'inserted', got '{r1}'"

        r2 = await svc._upsert_document(
            _row(content_id, 32519, sheet2),
            identifier_column="content_id",
            task_id=dedup_task_id,
        )
        await db.commit()

        result = await db.execute(
            select(Document).where(
                and_(Document.sheet_name == sheet2, Document.is_current == True)
            )
        )
        doc = result.scalars().first()

    assert doc is not None, "Current document not found after email 2"
    assert doc.video_views == 0, (
        f"FAIL: expected video_views=0 (32519 - 32519), got {doc.video_views}"
    )
    print(f"\nPASS  test 1: video_views={doc.video_views}  (expected 0)")


# ---------------------------------------------------------------------------
# Test 2 – same content_id, different values  =>  correct delta
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_subtract_delta_real_delta(dedup_task_id):
    content_id = "TEST_CONTENT_DELTA_002"
    sheet1 = f"{TEST_SHEET_PREFIX}d1"
    sheet2 = f"{TEST_SHEET_PREFIX}d2"

    async with _session_factory()() as db:
        svc = IngestionService(db)

        await svc._upsert_document(
            _row(content_id, 3091793, sheet1),
            identifier_column="content_id",
            task_id=dedup_task_id,
        )
        await db.commit()

        await svc._upsert_document(
            _row(content_id, 3095658, sheet2),
            identifier_column="content_id",
            task_id=dedup_task_id,
        )
        await db.commit()

        result = await db.execute(
            select(Document).where(
                and_(Document.sheet_name == sheet2, Document.is_current == True)
            )
        )
        doc = result.scalars().first()

    assert doc is not None, "Current document not found after email 2"
    assert doc.video_views == 3865, (
        f"FAIL: expected video_views=3865 (3095658 - 3091793), got {doc.video_views}"
    )
    print(f"\nPASS  test 2: video_views={doc.video_views}  (expected 3865)")


# ---------------------------------------------------------------------------
# Test 3 – old record marked stale, delta correct
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_old_record_marked_stale(dedup_task_id):
    content_id = "TEST_CONTENT_STALE_003"
    sheet1 = f"{TEST_SHEET_PREFIX}t1"
    sheet2 = f"{TEST_SHEET_PREFIX}t2"

    async with _session_factory()() as db:
        svc = IngestionService(db)

        await svc._upsert_document(
            _row(content_id, 100, sheet1),
            identifier_column="content_id",
            task_id=dedup_task_id,
        )
        await db.commit()

        await svc._upsert_document(
            _row(content_id, 150, sheet2),
            identifier_column="content_id",
            task_id=dedup_task_id,
        )
        await db.commit()

        old = (await db.execute(
            select(Document).where(Document.sheet_name == sheet1)
        )).scalars().first()

        current = (await db.execute(
            select(Document).where(
                and_(Document.content_id == content_id, Document.is_current == True)
            )
        )).scalars().all()

    assert old is not None
    assert old.is_current is False, (
        f"FAIL: old record should be is_current=False, got {old.is_current}"
    )
    assert len(current) == 1, f"FAIL: expected 1 current doc, got {len(current)}"
    assert current[0].video_views == 50, (
        f"FAIL: expected delta 50 (150-100), got {current[0].video_views}"
    )
    print(f"\nPASS  test 3: old is_current={old.is_current}, delta video_views={current[0].video_views}")


# ---------------------------------------------------------------------------
# Test 4 – connection match (different content_id, same text)  =>  NO delta
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connection_match_no_delta(dedup_task_id):
    cid1 = "TEST_CONN_1_004"
    cid2 = "TEST_CONN_2_004"
    title = "Shared article title for connection test 004"
    sheet1 = f"{TEST_SHEET_PREFIX}c1"
    sheet2 = f"{TEST_SHEET_PREFIX}c2"

    async with _session_factory()() as db:
        svc = IngestionService(db)

        r1 = _row(cid1, 1000, sheet1)
        r1["text"] = title
        await svc._upsert_document(
            r1,
            identifier_column="content_id",
            connection_strategy_column="text",
            task_id=dedup_task_id,
        )
        await db.commit()

        r2 = _row(cid2, 800, sheet2)
        r2["text"] = title
        await svc._upsert_document(
            r2,
            identifier_column="content_id",
            connection_strategy_column="text",
            task_id=dedup_task_id,
        )
        await db.commit()

        conn_doc = (await db.execute(
            select(Document).where(
                and_(Document.sheet_name == sheet2, Document.is_current == True)
            )
        )).scalars().first()

        both = (await db.execute(
            select(Document).where(
                and_(Document.text == title, Document.is_current == True)
            )
        )).scalars().all()

    assert conn_doc is not None
    assert conn_doc.video_views == 800, (
        f"FAIL: connection match should keep raw value 800, got {conn_doc.video_views}"
    )
    assert len(both) == 2, (
        f"FAIL: both connection-match records should be is_current=True, found {len(both)}"
    )
    print(f"\nPASS  test 4: video_views={conn_doc.video_views} (raw, no delta), both_current={len(both)}")
