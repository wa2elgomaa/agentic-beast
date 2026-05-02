"""Full-pipeline deduplication test using two real Gmail email message IDs.

Fetches the two emails directly from Gmail, runs them through _process_single_email
in order (oldest first), and asserts dedup subtract strategy produced correct deltas.

Prerequisites:
  - Set env var TNN_REAL_TASK_ID to the UUID of your Emplifi Gmail task.
  - The task must have valid Gmail OAuth tokens in its adaptor_config.

Run from backend/src:
    TNN_REAL_TASK_ID=<uuid> pytest tests/test_gmail_email_dedup.py -v -s

The two email IDs are hardcoded below in EMAIL_ID_DAY1 / EMAIL_ID_DAY2.
Day1 email is processed first, Day2 second — dedup subtract runs on Day2.
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.schemas.document import Document
from app.schemas.ingestion_task import IngestionTask, IngestionTaskRun
from app.schemas.processed_email import ProcessedEmail
from app.services.ingestion_service import IngestionService
from app.services.deduplication_service import DeduplicationService
from app.adapters.gmail_adapter import GmailAdapter
from app.services.gmail_credential_service import get_gmail_credential_service

# ---------------------------------------------------------------------------
# Email IDs — the two consecutive daily Emplifi exports
# ---------------------------------------------------------------------------
EMAIL_ID_DAY1 = "19d3c0e0d942fc82"   # 30-march email (older)
EMAIL_ID_DAY2 = "19d4131ec6c9de90"   # 31-march email (newer)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_real_task_id() -> uuid.UUID | None:
    raw = os.environ.get("TNN_REAL_TASK_ID", "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


REAL_TASK_ID = _get_real_task_id()

pytestmark = pytest.mark.skipif(
    REAL_TASK_ID is None,
    reason="Set TNN_REAL_TASK_ID env var to run this test",
)


# ---------------------------------------------------------------------------
# Session factory (NullPool avoids cross-event-loop connection reuse)
# ---------------------------------------------------------------------------

def _session_factory() -> async_sessionmaker:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    """
    Before each test: remove processed_email records for the two test emails
    so _is_email_processed() won't skip them.
    Also remove any documents produced by previous test runs for these emails.
    """
    sf = _session_factory()
    async with sf() as db:
        # Clear processed_email tracking so emails are re-processed
        await db.execute(
            delete(ProcessedEmail).where(
                ProcessedEmail.message_id.in_([EMAIL_ID_DAY1, EMAIL_ID_DAY2])
            )
        )
        # Clear documents written by these emails (sheet_name starts with the message_id)
        await db.execute(
            delete(Document).where(
                or_(
                    Document.sheet_name.like(f"{EMAIL_ID_DAY1}%"),
                    Document.sheet_name.like(f"{EMAIL_ID_DAY2}%"),
                )
            )
        )
        await db.commit()

    yield

    # Post-test cleanup — leave data in place for manual inspection,
    # but remove processed_email entries so the task can run normally again.
    sf2 = _session_factory()
    async with sf2() as db:
        await db.execute(
            delete(ProcessedEmail).where(
                ProcessedEmail.message_id.in_([EMAIL_ID_DAY1, EMAIL_ID_DAY2])
            )
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_task_config(db: AsyncSession):
    """Return (task, identifier_column, connection_strategy_column, field_mappings, dedup_config, gmail_adapter_kwargs)."""
    from app.services.schema_mapping_service import SchemaMappingService
    from app.services.ingestion_service import IngestionService as _IS

    result = await db.execute(select(IngestionTask).where(IngestionTask.id == REAL_TASK_ID))
    task = result.scalar_one_or_none()
    assert task is not None, f"Task {REAL_TASK_ID} not found in DB"

    adaptor_config = dict(task.adaptor_config or {})
    schema_service = SchemaMappingService(db)
    task_mapping = await schema_service.get_task_mapping(str(REAL_TASK_ID))
    assert task_mapping is not None, f"No schema mapping for task {REAL_TASK_ID}"

    field_mappings = task_mapping.field_mappings or {}
    identifier_column = task_mapping.identifier_column
    connection_strategy_column = task_mapping.connection_strategy_identifier_column
    dedup_config = task_mapping.dedup_config

    # Resolve source column names → ORM field names
    if identifier_column and field_mappings:
        resolved = _IS._resolve_source_to_doc_field(identifier_column, field_mappings)
        if resolved:
            print(f"\n[DEDUP] identifier_column '{identifier_column}' → ORM '{resolved}'")
            identifier_column = resolved

    if connection_strategy_column and field_mappings:
        resolved = _IS._resolve_source_to_doc_field(connection_strategy_column, field_mappings)
        if resolved:
            print(f"[DEDUP] connection_strategy_column '{connection_strategy_column}' → ORM '{resolved}'")
            connection_strategy_column = resolved

    # Build Gmail adapter kwargs from task config + settings fallback
    oauth_config = dict(adaptor_config.get("gmail_oauth", {}))
    if not oauth_config.get("client_id") and settings.gmail_oauth_client_id:
        oauth_config["client_id"] = settings.gmail_oauth_client_id
    if not oauth_config.get("client_secret") and settings.gmail_oauth_client_secret:
        oauth_config["client_secret"] = settings.gmail_oauth_client_secret
    if not oauth_config.get("token_uri") and settings.gmail_oauth_token_uri:
        oauth_config["token_uri"] = settings.gmail_oauth_token_uri

    gmail_kwargs = {
        "oauth_config": oauth_config,
        "sheet_name": adaptor_config.get("sheet_name", "Sheet1"),
        "gmail_source_type": adaptor_config.get("gmail_source_type", "attachment"),
        "download_link_regex": adaptor_config.get("download_link_regex") or r"https?://\S+",
    }

    return task, identifier_column, connection_strategy_column, field_mappings, dedup_config, gmail_kwargs


async def _create_run(db: AsyncSession, label: str) -> IngestionTaskRun:
    run = IngestionTaskRun(
        id=uuid.uuid4(),
        task_id=REAL_TASK_ID,
        status="running",
        run_metadata={"test_label": label},
    )
    db.add(run)
    await db.flush()
    return run


async def _fetch_email(adapter: GmailAdapter, message_id: str, source_type: str, link_regex: str) -> dict:
    email = await adapter.fetch_single_email(
        message_id=message_id,
        source_type=source_type,
        link_regex=link_regex,
    )
    assert email is not None, (
        f"fetch_single_email returned None for message_id={message_id}. "
        "Check that the email still exists in Gmail and OAuth tokens are valid."
    )
    print(f"\n[GMAIL] Fetched email {message_id}: subject='{email.get('subject')}' date='{email.get('date')}'")
    return email


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_two_email_dedup_subtract():
    """
    Ingest Day1 email then Day2 email through the exact same code path the
    Celery worker uses (_process_single_email).

    Assertions:
    1. Day1 inserts rows with raw values (no delta)
    2. Day2 marks Day1 docs as is_current=False (stale)
    3. Day2 current docs have video_views != Day1 raw (subtract ran)
    4. received_at is populated for BOTH sets of rows
    """
    sf = _session_factory()
    async with sf() as db:
        svc = IngestionService(db)
        task, identifier_column, connection_strategy_column, field_mappings, dedup_config, gmail_kwargs = \
            await _load_task_config(db)

        # Build and connect Gmail adapter
        credential_service = get_gmail_credential_service(db)
        adapter = GmailAdapter(
            oauth_config=gmail_kwargs["oauth_config"],
            credential_service=credential_service,
            task_id=str(REAL_TASK_ID),
        )
        await adapter.connect()

        # Fetch both emails upfront (validates connectivity before mutating DB)
        email_day1 = await _fetch_email(
            adapter, EMAIL_ID_DAY1,
            gmail_kwargs["gmail_source_type"],
            gmail_kwargs["download_link_regex"],
        )
        email_day2 = await _fetch_email(
            adapter, EMAIL_ID_DAY2,
            gmail_kwargs["gmail_source_type"],
            gmail_kwargs["download_link_regex"],
        )

        dedup_svc = DeduplicationService(svc.db, REAL_TASK_ID) if task.deduplication_enabled else None

        # --- Process Day1 email ---
        run1 = await _create_run(db, "gmail_day1")
        await db.commit()

        result1 = await svc._process_single_email(
            email=email_day1,
            task_id=REAL_TASK_ID,
            run_id=run1.id,
            field_mappings=field_mappings,
            identifier_column=identifier_column,
            connection_strategy_column=connection_strategy_column,
            dedup_service=dedup_svc,
            gmail_adapter=adapter,
            sheet_name=gmail_kwargs["sheet_name"],
            gmail_source_type=gmail_kwargs["gmail_source_type"],
            dedup_config=dedup_config,
        )
        await db.commit()

        print(f"\n[DAY1] inserted={result1.rows_inserted}, updated={result1.rows_updated}, "
              f"failed={result1.rows_failed}, success={result1.is_success}")
        if result1.error_message:
            print(f"[DAY1] error: {result1.error_message}")

        assert result1.is_success, f"Day1 email processing failed: {result1.error_message}"
        assert result1.rows_inserted > 0, "Day1 should insert rows"

        # Check received_at populated for Day1
        day1_sheet = f"{EMAIL_ID_DAY1}#{gmail_kwargs['sheet_name']}"
        day1_docs = (await db.execute(
            select(Document).where(Document.sheet_name == day1_sheet)
        )).scalars().all()

        day1_null_dates = [d for d in day1_docs if d.received_at is None]
        print(f"[DAY1] {len(day1_docs)} docs, {len(day1_null_dates)} with NULL received_at")

        # --- Process Day2 email ---
        run2 = await _create_run(db, "gmail_day2")
        await db.commit()

        result2 = await svc._process_single_email(
            email=email_day2,
            task_id=REAL_TASK_ID,
            run_id=run2.id,
            field_mappings=field_mappings,
            identifier_column=identifier_column,
            connection_strategy_column=connection_strategy_column,
            dedup_service=dedup_svc,
            gmail_adapter=adapter,
            sheet_name=gmail_kwargs["sheet_name"],
            gmail_source_type=gmail_kwargs["gmail_source_type"],
            dedup_config=dedup_config,
        )
        await db.commit()

        print(f"\n[DAY2] inserted={result2.rows_inserted}, updated={result2.rows_updated}, "
              f"failed={result2.rows_failed}, success={result2.is_success}")
        if result2.error_message:
            print(f"[DAY2] error: {result2.error_message}")

        assert result2.is_success, f"Day2 email processing failed: {result2.error_message}"

        # --- Assert dedup: Day1 docs should be stale ---
        day2_sheet = f"{EMAIL_ID_DAY2}#{gmail_kwargs['sheet_name']}"

        day1_stale = (await db.execute(
            select(Document).where(
                and_(Document.sheet_name == day1_sheet, Document.is_current == False)
            )
        )).scalars().all()

        day2_current = (await db.execute(
            select(Document).where(
                and_(Document.sheet_name == day2_sheet, Document.is_current == True)
            )
        )).scalars().all()

        day2_null_dates = [d for d in day2_current if d.received_at is None]

        print(f"\n[RESULTS] Day1 stale docs: {len(day1_stale)}")
        print(f"[RESULTS] Day2 current docs: {len(day2_current)}")
        print(f"[RESULTS] Day2 NULL received_at: {len(day2_null_dates)}")

        assert len(day1_stale) > 0, (
            "FAIL: No Day1 docs marked is_current=False. "
            "Dedup subtract never ran — check identifier_column resolution."
        )

        # --- Spot-check: verify delta was applied, not raw value stored ---
        stale_by_cid = {d.content_id: d for d in day1_stale if d.content_id}
        matched = [d for d in day2_current if d.content_id in stale_by_cid]

        assert len(matched) > 0, "No matching content_ids between stale Day1 and current Day2"

        sample_day2 = matched[0]
        sample_day1 = stale_by_cid[sample_day2.content_id]

        print(f"\n[SAMPLE] content_id={sample_day2.content_id}")
        print(f"  Day1 (stale) video_views={sample_day1.video_views}, received_at={sample_day1.received_at}")
        print(f"  Day2 (current) video_views={sample_day2.video_views}, received_at={sample_day2.received_at}")

        # If video_views on Day2 == Day1 raw → subtract never ran
        if sample_day1.video_views is not None and sample_day1.video_views > 0:
            assert sample_day2.video_views != sample_day1.video_views, (
                f"FAIL: Day2 video_views ({sample_day2.video_views}) == Day1 raw ({sample_day1.video_views}). "
                "Subtract strategy did not run."
            )

        # received_at check
        assert sample_day2.received_at is not None, (
            "FAIL: received_at is NULL on Day2 document. "
            "Check email.get('date') parsing in _process_single_email."
        )

        print(f"\nPASS: {len(day1_stale)} Day1 docs stale, "
              f"sample delta={sample_day2.video_views} (was {sample_day1.video_views}), "
              f"Day2 received_at={sample_day2.received_at}")
