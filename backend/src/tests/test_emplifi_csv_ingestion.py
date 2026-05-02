"""Full-pipeline deduplication test using real Emplifi CSV files.

Simulates what the Celery worker does for two consecutive daily exports:
  1. Parse CSV  (ExcelProcessor.parse_tabular_rows)
  2. Map columns to Document ORM fields  (_build_document_payload)
  3. Upsert with dedup strategy  (_upsert_document)

Day-1 file: emplifi-30-march-2026.csv
Day-2 file: emplifi-31-march-2026.csv

Rows that appear in both files with the same Content ID should have the
subtract-delta strategy applied on the second ingestion.

Run from backend/src:
    pytest tests/test_emplifi_csv_ingestion.py -v -s
"""

from pathlib import Path
import uuid
import pytest
import pytest_asyncio

from sqlalchemy import delete, select, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.processors.excel_processor import ExcelProcessor
from app.schemas.document import Document
from app.schemas.ingestion_task import IngestionTask, TaskSchemaMapping
from app.services.ingestion_service import IngestionService

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
DATA_DIR = Path(__file__).parents[2] / "data" / "analytics"
CSV_DAY1 = DATA_DIR / "emplifi-30-march-2026.csv"
CSV_DAY2 = DATA_DIR / "emplifi-31-march-2026.csv"

# ------------------------------------------------------------------
# Dedup config — mirrors the production task_schema_mappings entry
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# Field mappings: lower-cased CSV header  →  Document ORM field
# (mirrors what a user would configure in the SchemaMapper UI)
# ------------------------------------------------------------------
FIELD_MAPPINGS: dict[str, str] = {
    "date":                         "report_date",
    "profile name":                 "profile_name",
    "profile url":                  "profile_url",
    "profile id":                   "profile_id",
    "post detail url":              "post_detail_url",
    "content id":                   "content_id",
    "platform":                     "platform",
    "content type":                 "content_type",
    "media type":                   "media_type",
    "origin of the content":        "origin_of_the_content",
    "author url":                   "author_url",
    "author id":                    "author_id",
    "author name":                  "author_name",
    "content":                      "text",
    "view on platform":             "view_on_platform",
    "organic interactions":         "organic_interactions",
    "total interactions":           "total_interactions",
    "total reactions":              "total_reactions",
    "total comments":               "total_comments",
    "total shares":                 "total_shares",
    "engagements":                  "engagements",
    "total reach":                  "total_reach",
    "paid reach":                   "paid_reach",
    "organic reach":                "organic_reach",
    "total impressions":            "total_impressions",
    "paid impressions":             "paid_impressions",
    "organic impressions":          "organic_impressions",
    "video length (sec)":           "video_length_sec",
    "video view count":             "video_views",
    "total video view time (sec)":  "total_video_view_time_sec",
    "average time watched (sec)":   "avg_video_view_time_sec",
    "completion rate":              "completion_rate",
}

# identifier_column as it arrives in _upsert_document after the
# _resolve_source_to_doc_field step in ingest_task (ORM field name)
IDENTIFIER_COLUMN = "content_id"

# Sheet-name prefix used for all test rows — cleanup is keyed on this
SHEET_PREFIX = "TEST_EMPLIFI_SIM__"
DEDUP_TASK_NAME_PREFIX = "TEST_EMPLIFI_TASK__"

# ------------------------------------------------------------------
# Known assertions (content_id → {day1_val, day2_val, expected_delta})
# Derived from comparing the two CSV files
# ------------------------------------------------------------------
ASSERTIONS = [
    # facebook post — video_views grow by 30
    {
        "content_id": "148788988477345_1379640114192409",
        "platform":   "facebook",
        "metric":     "video_views",
        "day1_raw":   1008,
        "day2_raw":   1038,
        "expected_delta": 30,
    },
    # tiktok video — video_views grow by 12
    {
        "content_id": "7612642833702374667",
        "platform":   "tiktok",
        "metric":     "video_views",
        "day1_raw":   15475,
        "day2_raw":   15487,
        "expected_delta": 12,
    },
    # linkedin — video_views unchanged  (delta == 0)
    {
        "content_id": "7434628503746248705",
        "platform":   "linkedin",
        "metric":     "video_views",
        "day1_raw":   5228,
        "day2_raw":   5228,
        "expected_delta": 0,
    },
    # instagram — video_views grow by 1
    {
        "content_id": "18092097680107264",
        "platform":   "instagram",
        "metric":     "video_views",
        "day1_raw":   47696,
        "day2_raw":   47697,
        "expected_delta": 1,
    },
]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _session_factory() -> async_sessionmaker:
    """NullPool: no connection reuse across event loops."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


@pytest_asyncio.fixture
async def dedup_task_id():
    """Create a throw-away IngestionTask + TaskSchemaMapping with DEDUP_CONFIG.

    Yields the task UUID so _upsert_document can load dedup_config via _get_dedup_config(task_id).
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
            identifier_column=IDENTIFIER_COLUMN,
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


async def _ingest_csv(svc: IngestionService, csv_path: Path, sheet_name: str, task_id) -> dict:
    """Parse a CSV and upsert every row — mirrors _ingest_from_file_task logic.

    Returns a summary dict with inserted/updated/failed counts.
    """
    file_bytes = csv_path.read_bytes()
    raw_rows, parse_errors = ExcelProcessor.parse_tabular_rows(
        file_bytes, filename=csv_path.name, sheet_name=sheet_name
    )

    inserted = updated = failed = 0
    for raw_row in raw_rows:
        # Stamp with test sheet_name so cleanup is keyed on it
        raw_row["sheet_name"] = sheet_name

        try:
            doc_row = svc._build_document_payload(raw_row, FIELD_MAPPINGS)
            # Ensure sheet_name carries through
            doc_row["sheet_name"] = sheet_name

            result = await svc._upsert_document(
                doc_row,
                identifier_column=IDENTIFIER_COLUMN,
                task_id=task_id,
            )
            if result == "inserted":
                inserted += 1
            elif result in ("appended", "updated"):
                updated += 1
        except Exception as exc:
            failed += 1
            print(f"  ROW ERROR row={raw_row.get('row_number')} : {exc}")

    return {"inserted": inserted, "updated": updated, "failed": failed,
            "total": len(raw_rows), "parse_errors": len(parse_errors)}


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    sf = _session_factory()
    async with sf() as db:
        await db.execute(
            delete(Document).where(Document.sheet_name.like(f"{SHEET_PREFIX}%"))
        )
        await db.commit()
    yield
    sf2 = _session_factory()
    async with sf2() as db:
        await db.execute(
            delete(Document).where(Document.sheet_name.like(f"{SHEET_PREFIX}%"))
        )
        await db.commit()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emplifi_full_pipeline_dedup(dedup_task_id):
    """Ingest both daily CSV files and verify subtract-delta values."""

    sheet1 = f"{SHEET_PREFIX}30march"
    sheet2 = f"{SHEET_PREFIX}31march"

    async with _session_factory()() as db:
        svc = IngestionService(db)

        # ── Day 1: ingest emplifi-30-march-2026.csv ───────────────────────
        print(f"\n\n{'='*60}")
        print(f"Ingesting Day 1: {CSV_DAY1.name}")
        summary1 = await _ingest_csv(svc, CSV_DAY1, sheet1, dedup_task_id)
        await db.commit()
        print(f"  Day 1 result: {summary1}")
        assert summary1["failed"] == 0, f"Day 1 had {summary1['failed']} row failures"

        # ── Day 2: ingest emplifi-31-march-2026.csv ───────────────────────
        print(f"Ingesting Day 2: {CSV_DAY2.name}")
        summary2 = await _ingest_csv(svc, CSV_DAY2, sheet2, dedup_task_id)
        await db.commit()
        print(f"  Day 2 result: {summary2}")
        assert summary2["failed"] == 0, f"Day 2 had {summary2['failed']} row failures"

        # ── Assert dedup deltas for known content IDs ─────────────────────
        print(f"\n{'='*60}")
        print("Dedup assertions:")
        for case in ASSERTIONS:
            cid = case["content_id"]
            metric = case["metric"]
            expected = case["expected_delta"]

            # Current record for this content_id (from day 2 sheet)
            stmt = select(Document).where(
                and_(
                    Document.content_id == cid,
                    Document.sheet_name == sheet2,
                    Document.is_current == True,
                )
            )
            doc = (await db.execute(stmt)).scalars().first()

            assert doc is not None, (
                f"No current Day-2 record found for content_id={cid}"
            )

            actual = getattr(doc, metric)
            # SQLAlchemy returns Decimal/float for Numeric columns — normalise
            actual_int = int(actual) if actual is not None else None

            print(
                f"  {case['platform']:10s} {cid[:35]}  "
                f"day1={case['day1_raw']:>8}  day2_raw={case['day2_raw']:>8}  "
                f"stored={actual_int:>6}  expected_delta={expected}"
            )

            assert actual_int == expected, (
                f"FAIL  content_id={cid}  metric={metric}: "
                f"expected delta={expected}, got stored={actual_int}  "
                f"(day1_raw={case['day1_raw']}, day2_raw={case['day2_raw']})"
            )

            # Also verify the old Day-1 record is marked stale
            stmt_old = select(Document).where(
                and_(
                    Document.content_id == cid,
                    Document.sheet_name == sheet1,
                )
            )
            old_doc = (await db.execute(stmt_old)).scalars().first()
            assert old_doc is not None, f"Day-1 record missing for content_id={cid}"
            assert old_doc.is_current is False, (
                f"FAIL  Day-1 record should be is_current=False for content_id={cid}, "
                f"got {old_doc.is_current}"
            )

        print(f"\nAll {len(ASSERTIONS)} dedup assertions passed ✓")


@pytest.mark.asyncio
async def test_day1_only_rows_insert_with_raw_values():
    """Rows that exist only in Day 1 must be inserted with the raw (unmodified) values."""

    sheet1 = f"{SHEET_PREFIX}30march_only"

    # Content ID present only in day-1 file (verify no day-2 entry exists)
    # We pick a known day-1-only id by checking the CSVs beforehand:
    # python: set(day1_ids) - set(day2_ids)
    # Value determined by running the helper script that pre-computed this.
    # One concrete day-1-only id:
    DAY1_ONLY_CID = "148788988477345_1356270123196075"  # facebook, first row of day-1 CSV
    DAY1_VIDEO_VIEWS = 169288  # from the raw day-1 row

    async with _session_factory()() as db:
        svc = IngestionService(db)

        summary = await _ingest_csv(svc, CSV_DAY1, sheet1)
        await db.commit()

        stmt = select(Document).where(
            and_(
                Document.content_id == DAY1_ONLY_CID,
                Document.sheet_name == sheet1,
                Document.is_current == True,
            )
        )
        doc = (await db.execute(stmt)).scalars().first()

    assert doc is not None, f"Day-1-only record not found for {DAY1_ONLY_CID}"
    actual = int(doc.video_views) if doc.video_views is not None else None
    assert actual == DAY1_VIDEO_VIEWS, (
        f"FAIL: first-occurrence row should store raw value {DAY1_VIDEO_VIEWS}, got {actual}"
    )
    print(f"\nPASS  Day-1-only row: video_views={actual} (raw, no delta)")
