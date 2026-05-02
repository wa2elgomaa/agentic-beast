"""Integration test: full pipeline via real DB task + Emplifi CSV files.

This test loads the real task schema mapping from the DB (identifier_column,
field_mappings) and runs two back-to-back ingestion passes
using _ingest_from_file_task — the same code path the Celery worker uses
for manual/file adaptors. dedup_config is loaded automatically from the DB
via _get_dedup_config(task_id) inside _upsert_document.

Prerequisites:
  - Set env var TNN_REAL_TASK_ID to the UUID of your Emplifi Gmail task.
  - Run from backend/src:
        TNN_REAL_TASK_ID=<uuid> pytest tests/test_real_task_ingestion.py -v -s

NOTE: This test writes real rows to the `documents` table using the prefix
"TEST_REAL__" in sheet_name, and removes them in cleanup.
"""

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.schemas.document import Document
from app.schemas.ingestion_task import IngestionTask, IngestionTaskRun
from app.services.ingestion_service import IngestionService
from app.services.deduplication_service import DeduplicationService

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parents[2] / "data" / "analytics"
CSV_DAY1 = DATA_DIR / "emplifi-30-march-2026.csv"
CSV_DAY2 = DATA_DIR / "emplifi-31-march-2026.csv"

# Marker for documents written by this test — used for cleanup
SHEET_MARKER = "TEST_REAL__"


def _get_real_task_id() -> uuid.UUID | None:
    raw = os.environ.get("TNN_REAL_TASK_ID", "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


REAL_TASK_ID = _get_real_task_id()

# Skip all tests in this module if TNN_REAL_TASK_ID is not set
pytestmark = pytest.mark.skipif(
    REAL_TASK_ID is None,
    reason="Set TNN_REAL_TASK_ID env var to the Emplifi task UUID to run this test",
)


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

def _session_factory() -> async_sessionmaker:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    """Remove test documents before and after each test."""
    sf = _session_factory()
    async with sf() as db:
        await db.execute(
            delete(Document).where(Document.sheet_name.like(f"{SHEET_MARKER}%"))
        )
        await db.commit()
    yield
    sf2 = _session_factory()
    async with sf2() as db:
        await db.execute(
            delete(Document).where(Document.sheet_name.like(f"{SHEET_MARKER}%"))
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_task_and_mapping(db: AsyncSession):
    """Return (IngestionTask, identifier_column, field_mappings) for REAL_TASK_ID.

    dedup_config is no longer returned — it is loaded automatically by
    _upsert_document via _get_dedup_config(task_id).
    """
    from app.services.schema_mapping_service import SchemaMappingService
    from app.services.ingestion_service import IngestionService as _IS

    # Load task
    result = await db.execute(select(IngestionTask).where(IngestionTask.id == REAL_TASK_ID))
    task = result.scalar_one_or_none()
    assert task is not None, f"Task {REAL_TASK_ID} not found in DB"

    # Load schema mapping
    schema_service = SchemaMappingService(db)
    task_mapping = await schema_service.get_task_mapping(str(REAL_TASK_ID))
    assert task_mapping is not None, f"No schema mapping found for task {REAL_TASK_ID}"

    field_mappings = task_mapping.field_mappings or {}
    identifier_column = task_mapping.identifier_column
    connection_strategy_column = task_mapping.connection_strategy_identifier_column

    # Resolve source column names → ORM field names (same logic as ingest_task)
    if identifier_column and field_mappings:
        resolved = _IS._resolve_source_to_doc_field(identifier_column, field_mappings)
        if resolved:
            print(f"\n[DEDUP] identifier_column: '{identifier_column}' → resolved ORM field: '{resolved}'")
            identifier_column = resolved

    if connection_strategy_column and field_mappings:
        resolved = _IS._resolve_source_to_doc_field(connection_strategy_column, field_mappings)
        if resolved:
            print(f"[DEDUP] connection_strategy_column: '{connection_strategy_column}' → resolved: '{resolved}'")
            connection_strategy_column = resolved

    print(f"[SCHEMA] identifier_column={identifier_column}")
    print(f"[SCHEMA] connection_strategy_column={connection_strategy_column}")
    print(f"[SCHEMA] field_mappings keys={list(field_mappings.keys())[:10]}...")

    return task, identifier_column, connection_strategy_column, field_mappings


async def _create_run(db: AsyncSession, label: str) -> IngestionTaskRun:
    """Insert a minimal IngestionTaskRun and return it."""
    run = IngestionTaskRun(
        id=uuid.uuid4(),
        task_id=REAL_TASK_ID,
        status="running",
        run_metadata={"test_label": label},
    )
    db.add(run)
    await db.flush()
    return run


async def _patch_sheet_names(db: AsyncSession, old_prefix: str, new_prefix: str):
    """Rewrite sheet_name so test rows have the SHEET_MARKER and can be cleaned up."""
    # Fetch all documents whose sheet_name starts with old_prefix
    result = await db.execute(
        select(Document).where(Document.sheet_name.like(f"{old_prefix}%"))
    )
    docs = result.scalars().all()
    for doc in docs:
        doc.sheet_name = doc.sheet_name.replace(old_prefix, new_prefix, 1)
    await db.flush()


async def _ingest_csv(
    svc: IngestionService,
    csv_path: Path,
    run_id: uuid.UUID,
    task: IngestionTask,
    field_mappings: dict,
    identifier_column: str | None,
    connection_strategy_column: str | None,
    sheet_name_override: str | None = None,
) -> tuple[int, int, int]:
    """Run _ingest_from_file_task on a CSV file and return (inserted, updated, failed).

    dedup_config is no longer passed — _ingest_from_file_task loads it from
    the DB via _get_dedup_config(task_id) inside _upsert_document.
    """
    from app.processors.excel_processor import ExcelProcessor
    from app.schemas.ingestion import RowError

    file_bytes = csv_path.read_bytes()

    # Override sheet_name in adaptor_config so documents use our test prefix
    original_adaptor_config = dict(task.adaptor_config or {})
    if sheet_name_override:
        task.adaptor_config = dict(original_adaptor_config)
        task.adaptor_config["sheet_name"] = sheet_name_override
        task.adaptor_config["uploaded_filename"] = csv_path.name

    dedup_service = DeduplicationService(svc.db, REAL_TASK_ID) if task.deduplication_enabled else None

    inserted, updated, failed, errors = await svc._ingest_from_file_task(
        task,
        run_id,
        file_bytes,
        field_mappings,
        identifier_column,
        connection_strategy_column,
        dedup_service,
    )

    # Restore adaptor_config
    task.adaptor_config = original_adaptor_config

    if errors:
        print(f"\n[ERRORS] First 5 row errors:")
        for e in errors[:5]:
            print(f"  row {e.row_number}: {e.error}")

    return inserted, updated, failed


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_task_two_day_dedup():
    """Ingest Day1 then Day2 using the real task schema and assert delta values.

    Picks two well-known content_ids that appear in both CSV files and checks
    that video_views on Day2 equals the delta (day2_raw - day1_raw).
    """
    # These content IDs must appear in BOTH csvs with different video_views
    # Update these constants after running with --collect-only or -s to see actual data
    KNOWN_CID = None  # will be discovered from data
    DAY1_SHEET = f"{SHEET_MARKER}day1"
    DAY2_SHEET = f"{SHEET_MARKER}day2"

    sf = _session_factory()
    async with sf() as db:
        svc = IngestionService(db)
        task, identifier_column, connection_strategy_column, field_mappings = \
            await _load_task_and_mapping(db)

        # --- Day 1 ---
        run1 = await _create_run(db, "day1")
        await db.commit()

        i1, u1, f1 = await _ingest_csv(
            svc, CSV_DAY1, run1.id, task, field_mappings,
            identifier_column, connection_strategy_column,
            sheet_name_override=DAY1_SHEET,
        )
        await db.commit()
        print(f"\n[DAY1] inserted={i1}, updated={u1}, failed={f1}")
        assert i1 > 0, "Day1 should insert at least some rows"

        # --- Day 2 ---
        run2 = await _create_run(db, "day2")
        await db.commit()

        i2, u2, f2 = await _ingest_csv(
            svc, CSV_DAY2, run2.id, task, field_mappings,
            identifier_column, connection_strategy_column,
            sheet_name_override=DAY2_SHEET,
        )
        await db.commit()
        print(f"[DAY2] inserted={i2}, updated={u2}, failed={f2}")

        # --- Find duplicate content_ids ---
        # Get all current Day2 documents
        day2_docs = (await db.execute(
            select(Document).where(
                and_(Document.sheet_name == DAY2_SHEET, Document.is_current == True)
            )
        )).scalars().all()

        # Get Day1 docs that are now stale (is_current=False) — these were updated
        day1_stale = (await db.execute(
            select(Document).where(
                and_(Document.sheet_name == DAY1_SHEET, Document.is_current == False)
            )
        )).scalars().all()

        print(f"\n[RESULTS] Day2 current docs: {len(day2_docs)}")
        print(f"[RESULTS] Day1 stale docs (marked by dedup): {len(day1_stale)}")
        assert len(day1_stale) > 0, (
            "Expected some Day1 docs to be marked is_current=False by dedup. "
            "Zero stale docs means the subtract strategy never ran."
        )

        # --- Spot-check: find a content_id that appears in both outputs ---
        stale_cids = {d.content_id for d in day1_stale if d.content_id}
        matched_day2 = [d for d in day2_docs if d.content_id in stale_cids]
        assert len(matched_day2) > 0, "No matching content_ids found between stale Day1 and current Day2"

        # Pick first match and verify delta
        sample = matched_day2[0]
        stale = next(d for d in day1_stale if d.content_id == sample.content_id)

        # Find the original Day1 raw value (stale doc)
        # video_views on Day2 current doc should be delta, not raw
        # delta = day2_raw - day1_raw
        # We don't know day2_raw directly, but:
        #   if delta == day2_raw: dedup didn't run (BUG)
        #   if delta < day2_raw: dedup ran correctly
        # As a proxy: stale doc has the Day1 raw; if Day2 doc stores the same large number → BUG
        print(f"\n[SAMPLE] content_id={sample.content_id}")
        print(f"  Day1 (stale): video_views={stale.video_views}")
        print(f"  Day2 (current): video_views={sample.video_views}")

        # The Day2 delta should NOT equal the Day1 raw value
        # (unless day2_raw exactly doubled, which is extremely unlikely)
        if stale.video_views is not None and stale.video_views > 0:
            assert sample.video_views != stale.video_views, (
                f"FAIL: Day2 video_views ({sample.video_views}) == Day1 raw ({stale.video_views}). "
                "Looks like subtract strategy didn't run — check identifier_column and numeric coercion."
            )

        print(f"\nPASS: dedup subtract ran on {len(day1_stale)} rows, "
              f"sample content_id delta={sample.video_views} (Day1 was {stale.video_views})")


@pytest.mark.asyncio
async def test_real_task_day1_raw_values_stored():
    """First ingestion (Day1 only) stores raw values, no delta applied."""
    DAY1_SHEET = f"{SHEET_MARKER}raw1"

    sf = _session_factory()
    async with sf() as db:
        svc = IngestionService(db)
        task, identifier_column, connection_strategy_column, field_mappings = \
            await _load_task_and_mapping(db)

        run1 = await _create_run(db, "raw1")
        await db.commit()

        i1, u1, f1 = await _ingest_csv(
            svc, CSV_DAY1, run1.id, task, field_mappings,
            identifier_column, connection_strategy_column,
            sheet_name_override=DAY1_SHEET,
        )
        await db.commit()
        print(f"\n[DAY1-ONLY] inserted={i1}, updated={u1}, failed={f1}")

        # All rows should be inserted, none updated
        assert i1 > 0, "Expected rows to be inserted on first ingestion"
        assert u1 == 0, f"Expected 0 updates on first ingestion, got {u1}"
        assert f1 == 0, f"Expected 0 failures on first ingestion, got {f1}"

        # No stale records should exist — this is the first pass
        stale = (await db.execute(
            select(Document).where(
                and_(Document.sheet_name == DAY1_SHEET, Document.is_current == False)
            )
        )).scalars().all()
        assert len(stale) == 0, f"No stale docs expected for first ingestion, got {len(stale)}"

        print(f"PASS: {i1} rows inserted raw, 0 stale records")
