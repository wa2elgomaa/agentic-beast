"""Service for orchestrating data ingestion pipeline."""

import hashlib
import json
import uuid
from datetime import date, datetime, time
from uuid import UUID

import httpx
from sqlalchemy import and_, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.adapters.gmail_adapter import (
    CredentialExpiredError,
    GmailAdapter,
    TemporaryAuthError,
)
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.models import (
    Document,
    IngestionTask,
    IngestionTaskRun,
    ProcessedEmail,
    RunStatus,
)
from app.processors.excel_processor import ExcelProcessor
from app.schemas.ingestion import IngestResult, RowError
from app.services.content_normalizer import ContentNormalizer
from app.services.deduplication_service import DeduplicationService
from app.services.email_processing_result import EmailProcessingResult
from app.services.embedding_service import get_embedding_service
from app.services.gmail_credential_service import (
    get_gmail_credential_service,
)
from app.services.schema_mapping_service import SchemaMappingService
from app.services.summary_service import get_summary_service

logger = get_logger(__name__)


class IngestionCanceledError(Exception):
    """Raised when a task run is stopped while ingestion is in progress."""

    def __init__(self, rows_inserted: int = 0, rows_updated: int = 0, rows_failed: int = 0):
        super().__init__("Canceled by user")
        self.rows_inserted = rows_inserted
        self.rows_updated = rows_updated
        self.rows_failed = rows_failed


class IngestionService:
    """Service for managing data ingestion pipeline."""

    def __init__(self, db_session: AsyncSession):
        """Initialize ingestion service."""
        self.db = db_session

    async def _safe_execute(self, stmt):
        """Execute a statement, and if the current transaction is aborted,
        rollback and retry the statement in a fresh session.

        Returns the result of `execute` on success. Raises the final
        exception on failure.
        """
        try:
            return await self.db.execute(stmt)
        except Exception as e:
            msg = str(e).lower()
            if "current transaction is aborted" in msg or "in failed sql transaction" in msg or "current transaction is in failed state" in msg:
                try:
                    await self.db.rollback()
                except Exception:
                    # best-effort rollback; continue to fresh session
                    pass
                async with AsyncSessionLocal() as fresh_sess:
                    try:
                        result = await fresh_sess.execute(stmt)
                        await fresh_sess.commit()
                        return result
                    except Exception:
                        await fresh_sess.rollback()
                        raise
            # not a transaction-abort case; re-raise
            raise

    @staticmethod
    def _source_key_to_column(source_key: str) -> str:
        """Resolve stored source mapping key to actual row column name.

        Source keys may include a duplicate suffix (e.g. "Total Reach::dup::1")
        to allow one source column to map to multiple DB fields.
        """
        return source_key.split("::dup::", 1)[0]

    @staticmethod
    def _coerce_document_value(field_name: str, value):
        """Normalize raw values before persisting to Document columns."""
        if isinstance(value, datetime) and field_name in {"published_date", "reported_at"}:
            return value.date()
        return value

    @staticmethod
    def _coerce_reported_time(reported_time_value: object | None) -> time | None:
        """Extract time-of-day from various source formats.

        Tries:
        1. If value is already a time object → return as-is
        2. If value is a datetime object → extract .time()
        3. If value is a string → try parsing as HH:MM:SS format
        4. Otherwise (None, etc.) → return None

        Args:
            reported_time_value: Raw value from source data

        Returns:
            time object or None
        """
        if reported_time_value is None:
            return None

        # Already a time object
        if isinstance(reported_time_value, time):
            return reported_time_value

        # Extract from datetime
        if isinstance(reported_time_value, datetime):
            return reported_time_value.time()

        # Try parsing string
        if isinstance(reported_time_value, str):
            reported_time_value = reported_time_value.strip()
            if not reported_time_value:
                return None
            try:
                # Try HH:MM:SS or HH:MM format
                parts = reported_time_value.split(":")
                if len(parts) >= 2:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    second = int(parts[2]) if len(parts) > 2 else 0
                    return time(hour, minute, second)
            except (ValueError, IndexError):
                pass

        return None

    @staticmethod
    def _metric_fingerprint(row_data: dict) -> str:
        """Compute hash of key metrics to detect changes.

        Only includes metrics that are meaningful for change detection,
        ignoring derived fields like is_current, timestamps, etc.

        Args:
            row_data: Document row data dict

        Returns:
            SHA256 hex digest of key metrics
        """
        # Key metrics that indicate a real change in data
        key_metrics = [
            "video_views",
            "total_video_view_time_sec",
            "avg_video_view_time_sec",
            "completion_rate",
            "total_interactions",
            "total_reach",
            "organic_reach",
            "paid_reach",
            "total_impressions",
            "organic_impressions",
            "paid_impressions",
            "total_reactions",
            "total_comments",
            "total_shares",
        ]

        metrics_dict = {k: row_data.get(k) for k in key_metrics}
        metrics_json = json.dumps(metrics_dict, sort_keys=True, default=str)
        return hashlib.sha256(metrics_json.encode()).hexdigest()

    @staticmethod
    def _document_column_names() -> set[str]:
        """Set of Document column names that can be supplied on insert/update."""
        return {
            column.name
            for column in Document.__table__.columns
            if column.name not in {"id", "created_at", "updated_at", "embedding"}
        }

    def _build_document_payload(self, source_row: dict, field_mappings: dict) -> dict:
        """Build a sanitized Document payload from a raw source row and saved field mappings."""
        allowed_columns = self._document_column_names()

        mapped_data = {}
        for source_key, target_field in (field_mappings or {}).items():
            source_column = self._source_key_to_column(source_key)
            if target_field not in allowed_columns:
                continue
            if source_column in source_row:
                mapped_data[target_field] = self._coerce_document_value(target_field, source_row[source_column])

        # Allow direct passthrough for already-normalized document columns.
        for key, value in source_row.items():
            if key in allowed_columns and key not in mapped_data:
                mapped_data[key] = self._coerce_document_value(key, value)

        source_metadata = {
            key: self._to_json_safe_value(value)
            for key, value in source_row.items()
            if key not in {"sheet_name", "row_number"}
        }

        text_value = mapped_data.get("text") or mapped_data.get("content") or mapped_data.get("title")
        if not text_value:
            text_parts = [
                str(mapped_data.get("title") or "").strip(),
                str(mapped_data.get("content") or "").strip(),
                str(mapped_data.get("description") or "").strip(),
                str(mapped_data.get("profile_name") or "").strip(),
                str(mapped_data.get("platform") or "").strip(),
            ]
            text_value = " ".join(part for part in text_parts if part).strip() or f"Row {source_row.get('row_number', 0)}"

        # Populate reported_time: try source field first, fallback to reported_at, then to ingestion time
        reported_time_value = None
        if mapped_data.get("reported_time"):
            # Already mapped from source
            reported_time_value = self._coerce_reported_time(mapped_data["reported_time"])
        elif source_row.get("reported_at"):
            # Try to extract time from reported_at
            reported_time_value = self._coerce_reported_time(source_row["reported_at"])
        if not reported_time_value:
            # Fallback to current ingestion time
            reported_time_value = datetime.now().time()

        # Ensure sheet_name and row_number are present
        sheet_name = source_row.get("sheet_name") or mapped_data.get("sheet_name") or "Sheet1"
        row_number = source_row.get("row_number") or mapped_data.get("row_number") or 0

        payload = {
            "sheet_name": sheet_name,
            "row_number": row_number,
            "text": str(text_value),
            "reported_time": reported_time_value,
            "doc_metadata": {"source_row": source_metadata},
        }
        payload.update(mapped_data)

        # Protect required fields from being overwritten with None
        # text cannot be null - ensure it has a value
        if not payload.get("text") or payload["text"] == "None":
            payload["text"] = f"Row {row_number}"

        # Sanitize nulls: numeric fields default to 0, booleans to False
        numeric_defaults = [
            "video_views",
            "total_video_view_time_sec",
            "avg_video_view_time_sec",
            "total_interactions",
            "total_reach",
            "total_impressions",
            "total_reactions",
            "total_comments",
            "total_shares",
            "engagements",
        ]
        for fld in numeric_defaults:
            if fld in payload and payload[fld] is None:
                payload[fld] = 0

        # Ensure is_current default if not set
        if "is_current" not in payload:
            payload["is_current"] = True

        # beast_uuid handling: use mapped content identifier if provided, else preserve existing or generate
        # If mapping indicated a content identifier target, it will have been mapped into payload already.
        if payload.get("beast_uuid"):
            # attempt to keep provided uuid (could be string)
            try:
                payload["beast_uuid"] = uuid.UUID(str(payload["beast_uuid"]))
            except Exception:
                # ignore invalid uuid and generate a new one
                payload["beast_uuid"] = uuid.uuid4()
        else:
            # generate a new UUID for this row so future ingests can match
            payload["beast_uuid"] = uuid.uuid4()
        return payload

    @staticmethod
    def _to_json_safe_value(value):
        """Convert values to JSON-serializable shapes for JSONB metadata."""
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, dict):
            return {str(k): IngestionService._to_json_safe_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [IngestionService._to_json_safe_value(v) for v in value]
        return value

    async def _is_run_stop_requested(self, run_id: UUID) -> bool:
        """Check whether a task run has been canceled or received a stop request."""
        stmt = (
            select(IngestionTaskRun)
            .where(IngestionTaskRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            return False

        run_metadata = run.run_metadata or {}
        return run.status == RunStatus.CANCELED or bool(run_metadata.get("cancel_requested"))

    async def _is_email_processed(self, message_id: str) -> bool:
        """Return True if this Gmail message_id has already been ingested."""
        stmt = select(ProcessedEmail).where(ProcessedEmail.message_id == message_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _record_processed_email(
        self,
        message_id: str,
        subject: str | None = None,
        sender: str | None = None,
        task_id: UUID | None = None,
        rows_inserted: int = 0,
        rows_updated: int = 0,
        rows_skipped: int = 0,
        rows_failed: int = 0,
        is_success: bool = True,
        is_retryable: bool = False,
    ) -> None:
        """Persist a ProcessedEmail record. Silently ignores duplicate inserts.

        Args:
            message_id: Gmail message ID
            subject: Email subject for audit
            sender: Email sender for audit
            task_id: Task ID if processed from a task
            rows_inserted: Rows inserted from this email
            rows_updated: Rows updated from this email
            rows_skipped: Rows skipped from this email
            rows_failed: Rows that failed from this email
            is_success: Whether email was successfully processed (True = all rows succeeded or 0 rows with no errors)
            is_retryable: Whether email should be queued for retry
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(ProcessedEmail)
            .values(
                message_id=message_id,
                task_id=task_id,
                subject=subject,
                sender=sender,
                rows_inserted=rows_inserted,
                rows_updated=rows_updated,
                rows_skipped=rows_skipped,
                rows_failed=rows_failed,
                is_success=is_success,
                is_retryable=is_retryable,
                processed_at=func.now(),
            )
            .on_conflict_do_nothing(index_elements=["message_id"])
        )
        await self.db.execute(stmt)

    async def ingest_from_gmail(self, identifier_column: str | None = None) -> IngestResult:
        """Fetch and ingest data from Gmail attachments.

        Args:
            identifier_column: Optional column name for cross-platform deduplication.

        Returns:
            Ingestion result with counts and errors.
        """
        logger.info("Starting Gmail ingestion")

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors = []

        try:
            # Connect to Gmail
            gmail_adapter = GmailAdapter()
            await gmail_adapter.connect()

            # Fetch emails
            emails = await gmail_adapter.fetch_data()

            # Process each email
            for email in emails:
                email_message_id = email.get("message_id", "")
                email_subject = email.get("subject", "")
                email_sender = email.get("from", "")

                # Skip already-processed emails
                if email_message_id and await self._is_email_processed(email_message_id):
                    logger.info(
                        "Skipping already-processed email",
                        message_id=email_message_id,
                        subject=email_subject,
                    )
                    continue

                logger.info("Processing email", subject=email_subject)
                email_inserted = 0
                email_skipped = 0
                email_failed = 0

                # Process attachments
                for attachment in email.get("attachments", []):
                    if not attachment["filename"].lower().endswith(".xlsx"):
                        logger.warning("Skipping non-Excel attachment", filename=attachment["filename"])
                        continue

                    # Parse Excel
                    excel_rows, parse_errors = ExcelProcessor.parse_excel(
                        attachment["data"],
                        sheet_name="Sheet1",
                    )

                    errors.extend(parse_errors)
                    rows_failed += len(parse_errors)

                    # Insert/upsert rows
                    for row_data in excel_rows:
                        try:
                            result = await self._upsert_document(row_data, identifier_column=identifier_column)
                            if result == "inserted":
                                rows_inserted += 1
                                email_inserted += 1
                            elif result == "skipped":
                                email_skipped += 1
                            else:
                                rows_updated += 1
                                email_inserted += 1

                        except Exception as e:
                            logger.error("Error upserting document", error=str(e))
                            errors.append(
                                RowError(
                                    row_number=row_data.get("row_number", 0),
                                    error=f"Database error: {e!s}",
                                )
                            )
                            rows_failed += 1
                            email_failed += 1

                # Record email as processed in DB and remove UNREAD label
                if email_message_id:
                    await self._record_processed_email(
                        message_id=email_message_id,
                        subject=email_subject,
                        sender=email_sender,
                        rows_inserted=email_inserted,
                        rows_skipped=email_skipped,
                        rows_failed=email_failed,
                    )
                try:
                    gmail_service = gmail_adapter.service
                    if gmail_service is not None:
                        await gmail_service.users().messages().modify(
                            userId="me",
                            id=email_message_id,
                            body={"removeLabelIds": ["UNREAD"]},
                        ).execute()
                except Exception as e:
                    logger.warning("Could not mark email as processed", error=str(e))

            await gmail_adapter.disconnect()

        except Exception as e:
            logger.error("Gmail ingestion failed", error=str(e))
            errors.append(RowError(row_number=0, error=f"Gmail adapter error: {e!s}"))

        # Trigger summary recomputation
        if rows_inserted > 0 or rows_updated > 0:
            try:
                summary_service = get_summary_service(self.db)
                await summary_service.compute_daily_summaries()
            except Exception as e:
                logger.warning("Summary computation failed", error=str(e))

        logger.info(
            "Gmail ingestion complete",
            inserted=rows_inserted,
            updated=rows_updated,
            failed=rows_failed,
        )

        return IngestResult(
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            rows_failed=rows_failed,
            errors=errors,
        )

    async def ingest_from_file(self, file_data: bytes, filename: str, identifier_column: str | None = None) -> IngestResult:
        """Ingest data from uploaded file.

        Args:
            file_data: Raw file bytes.
            filename: Original filename.
            identifier_column: Optional column name for cross-platform deduplication.

        Returns:
            Ingestion result.
        """
        logger.info("Starting file ingestion", filename=filename)

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors = []

        try:
            # Parse Excel
            excel_rows, parse_errors = ExcelProcessor.parse_excel(file_data)

            errors.extend(parse_errors)
            rows_failed = len(parse_errors)

            # Insert/upsert rows
            for row_data in excel_rows:
                try:
                    result = await self._upsert_document(row_data, identifier_column=identifier_column)
                    if result == "inserted":
                        rows_inserted += 1
                    elif result == "updated":
                        rows_updated += 1

                except Exception as e:
                    logger.error("Error upserting document", error=str(e))
                    errors.append(
                        RowError(
                            row_number=row_data.get("row_number", 0),
                            error=f"Database error: {e!s}",
                        )
                    )
                    rows_failed += 1

        except Exception as e:
            logger.error("File ingestion failed", error=str(e))
            errors.append(RowError(row_number=0, error=f"File processing error: {e!s}"))

        # Trigger summary recomputation
        if rows_inserted > 0 or rows_updated > 0:
            try:
                summary_service = get_summary_service(self.db)
                await summary_service.compute_daily_summaries()
            except Exception as e:
                logger.warning("Summary computation failed", error=str(e))

        logger.info(
            "File ingestion complete",
            inserted=rows_inserted,
            updated=rows_updated,
            failed=rows_failed,
        )

        return IngestResult(
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            rows_failed=rows_failed,
            errors=errors,
        )

    async def _upsert_document(self, row_data: dict, identifier_column: str | None = None) -> str:
        """Insert or append document record with full history tracking.

        Implements append-only history: instead of updating, creates new row
        if metrics have changed. Marks old record as stale (is_current=FALSE).

        When task_schema_mapping is provided with identifier_column configured,
        performs cross-platform deduplication using normalized content identifiers.

        Args:
            row_data: Row data dict.
            task_schema_mapping: Optional schema mapping with identifier_column for cross-platform matching.

        Returns:
            'inserted' (new record), 'appended' (metrics changed), or 'skipped' (no change).
        """
        # Keep each row write isolated so one bad row does not abort the full run transaction.
        async with self.db.begin_nested():
            # Ensure is_current defaults to TRUE if not set
            if "is_current" not in row_data:
                row_data["is_current"] = True

            # Protect required NOT NULL fields from being set to None
            if not row_data.get("text") or row_data.get("text") == "None":
                # Generate fallback text from available fields
                fallback_text = " ".join(
                    part for part in [
                        str(row_data.get("title") or "").strip(),
                        str(row_data.get("content") or "").strip(),
                        str(row_data.get("description") or "").strip(),
                    ] if part
                )
                row_data["text"] = fallback_text or f"Row {row_data.get('row_number', 0)}"

            # Convert NULL numeric values to 0 for accurate metric calculations
            numeric_fields = [
                "organic_interactions", "total_interactions", "total_reactions", "total_comments",
                "total_shares", "engagements", "total_reach", "paid_reach", "organic_reach",
                "total_impressions", "paid_impressions", "organic_impressions", "reach_engagement_rate",
                "total_likes", "video_length_sec", "video_views", "total_video_view_time_sec",
                "avg_video_view_time_sec", "completion_rate"
            ]
            for field in numeric_fields:
                if field in row_data and row_data[field] is None:
                    row_data[field] = 0

            # Attempt cross-platform matching if identifier_column is configured
            existing = None
            if identifier_column:
                identifier_value = row_data.get(identifier_column)

                if identifier_value:
                    # Normalize and hash the identifier for cross-platform matching
                    try:
                        identifier_cleaned, identifier_hash = ContentNormalizer.normalize(str(identifier_value))
                        row_data["identifier_cleaned"] = identifier_cleaned
                        row_data["identifier_hash"] = identifier_hash

                        # Query for match across any sheet/platform using identifier hash
                        stmt = select(Document).where(
                            and_(
                                Document.identifier_hash == identifier_hash,
                                Document.is_current,
                            )
                        )
                        result = await self.db.execute(stmt)
                        existing = result.scalars().first()

                        if existing:
                            logger.debug(
                                "Found existing document via cross-platform identifier match",
                                identifier_column=identifier_column,
                                identifier_hash=identifier_hash,
                                existing_id=existing.id,
                            )
                    except Exception as e:
                        logger.warning(
                            "Error during identifier normalization; falling back to legacy matching",
                            error=str(e),
                        )

            # Fallback: legacy sheet_name + row_number matching if cross-platform didn't find match
            if not existing:
                stmt = select(Document).where(
                    and_(
                        Document.sheet_name == row_data.get("sheet_name"),
                        Document.row_number == row_data.get("row_number"),
                        Document.is_current,
                    )
                )
                result = await self.db.execute(stmt)
                existing = result.scalars().first()

            # Generate embedding if needed
            embedding_service = get_embedding_service()
            profile_name = row_data.get("profile_name", "")
            text_to_embed = f"{profile_name} {row_data.get('platform', '')}"

            if text_to_embed.strip():
                try:
                    row_data["embedding"] = embedding_service.embed_text(text_to_embed)
                except Exception as e:
                    logger.warning("Could not generate embedding", error=str(e))

            # Compute metric fingerprint
            new_fingerprint = self._metric_fingerprint(row_data)

            if existing:
                # Extract metrics from existing record to compute its fingerprint
                existing_data = {
                    column.name: getattr(existing, column.name)
                    for column in Document.__table__.columns
                }
                old_fingerprint = self._metric_fingerprint(existing_data)

                # Check if metrics have changed
                if new_fingerprint == old_fingerprint:
                    # No change detected; skip insert to avoid spurious duplicates
                    logger.debug(
                        "Document metrics unchanged, skipping new version",
                        row_number=row_data.get("row_number"),
                        fingerprint=new_fingerprint,
                    )
                    return "skipped"

                # Calculate metric deltas before marking old as stale
                metric_deltas = self._calculate_metric_deltas(existing_data, row_data)
                if metric_deltas:
                    row_data["metric_deltas"] = metric_deltas

                # Note: Deduplication strategies are applied in _upsert_document_with_dedup_tracking
                # This method (_upsert_document) is the simple path without dedup strategies

                # Reuse existing beast_uuid if available, otherwise generate new
                if existing.beast_uuid:
                    row_data["beast_uuid"] = existing.beast_uuid
                else:
                    row_data["beast_uuid"] = uuid.uuid4()

                # Metrics changed: mark old record as stale and insert new version
                logger.debug(
                    "Document metrics changed, appending new version",
                    row_number=row_data.get("row_number"),
                    old_fingerprint=old_fingerprint,
                    new_fingerprint=new_fingerprint,
                    beast_uuid=row_data.get("beast_uuid"),
                )
                stmt = (
                    update(Document)
                    .where(Document.id == existing.id)
                    .values(is_current=False)
                )
                await self._safe_execute(stmt)

                # Insert new version with is_current=TRUE
                stmt = insert(Document).values(**row_data)
                try:
                    await self._safe_execute(stmt)
                    return "appended"
                except IntegrityError as e:
                    # Fallback for race conditions where unique index prevents insert
                    logger.warning(
                        "Insert conflict on append; falling back to updating existing row",
                        sheet_name=row_data.get("sheet_name"),
                        row_number=row_data.get("row_number"),
                        error=str(e),
                    )
                    # Update the current record in-place instead
                    upd_stmt = (
                        update(Document)
                        .where(
                            and_(Document.sheet_name == row_data.get("sheet_name"), Document.row_number == row_data.get("row_number"))
                        )
                        .values(**{k: v for k, v in row_data.items() if k != "id"})
                    )
                    await self._safe_execute(upd_stmt)
                    return "updated"
            else:
                # New record: assign fresh beast_uuid and insert with is_current=TRUE
                row_data["beast_uuid"] = uuid.uuid4()
                row_data["metric_deltas"] = None  # First ingestion has no deltas

                stmt = insert(Document).values(**row_data)
                try:
                    await self._safe_execute(stmt)
                    logger.debug("Document inserted", row_number=row_data.get("row_number"), beast_uuid=row_data.get("beast_uuid"))
                    return "inserted"
                except IntegrityError as e:
                    logger.warning(
                        "Insert conflict on insert; falling back to updating existing row",
                        sheet_name=row_data.get("sheet_name"),
                        row_number=row_data.get("row_number"),
                        error=str(e),
                    )
                    upd_stmt = (
                        update(Document)
                        .where(
                            and_(Document.sheet_name == row_data.get("sheet_name"), Document.row_number == row_data.get("row_number"))
                        )
                        .values(**{k: v for k, v in row_data.items() if k != "id"})
                    )
                    await self._safe_execute(upd_stmt)
                    return "updated"

    def _calculate_metric_deltas(self, existing_data: dict, new_data: dict) -> dict | None:
        """Calculate metric deltas (differences) between old and new values.

        Returns:
            Dict of {metric_name: delta} for metrics that changed, or None if no deltas.
        """
        # Metric columns to track (from Document model)
        metric_columns = {
            "video_views", "total_reach", "engagements", "shares", "comments",
            "likes", "total_impressions", "profile_views", "followers_gained",
            "followers_lost", "total_followers", "message_count", "message_reach",
            "message_engagement", "clicks", "utm_source", "utm_medium", "utm_campaign"
        }

        deltas = {}
        for metric in metric_columns:
            if metric in existing_data and metric in new_data:
                prev_val = existing_data.get(metric) or 0
                new_val = new_data.get(metric) or 0

                # Skip non-numeric values
                if not isinstance(prev_val, (int, float)) or not isinstance(new_val, (int, float)):
                    continue

                delta = new_val - prev_val
                if delta != 0:
                    deltas[metric] = delta

        return deltas if deltas else None

    def _apply_dedup_strategies(
        self,
        row_data: dict,
        existing_data: dict,
        dedup_config: dict | None,
    ) -> dict:
        """Apply deduplication strategies to metric fields in row_data.

        When a duplicate is found and dedup_config is provided, applies the configured
        strategy to each metric field:
        - subtract: new_value - previous_value (for delta metrics like daily views)
        - keep: new_value only (for current state like follower count)
        - add/sum: new_value + previous_value (for cumulative like lifetime reach)
        - skip: don't include this field (completely skip duplicate)

        Args:
            row_data: New row data being ingested
            existing_data: Existing row data from database
            dedup_config: Dedup config with {default_strategy, field_strategies, is_metric}

        Returns:
            Modified row_data with strategies applied to metric fields.
        """
        if not dedup_config:
            # No config: default to subtract for all metrics (backward compatible)
            return row_data

        # Metric columns to track
        metric_columns = {
            "video_views", "total_reach", "engagements", "shares", "comments",
            "likes", "total_impressions", "profile_views", "followers_gained",
            "followers_lost", "total_followers", "message_count", "message_reach",
            "message_engagement", "clicks", "utm_source", "utm_medium", "utm_campaign"
        }

        is_metric = dedup_config.get("is_metric", {})
        default_strategy = dedup_config.get("default_strategy", "subtract")
        field_strategies = dedup_config.get("field_strategies", {})

        applied_strategies = {}
        for metric in metric_columns:
            # Only process if this field is marked as metric
            if not is_metric.get(metric, False):
                continue

            if metric not in row_data or metric not in existing_data:
                continue

            prev_val = existing_data.get(metric) or 0
            new_val = row_data.get(metric) or 0

            # Skip non-numeric values
            if not isinstance(prev_val, (int, float)) or not isinstance(new_val, (int, float)):
                continue

            # Get the strategy for this field (override or default)
            strategy = field_strategies.get(metric, default_strategy)

            if strategy == "skip":
                # Skip completely - don't store this metric for duplicates
                row_data.pop(metric, None)
                applied_strategies[metric] = "skip"
            elif strategy == "keep":
                # Keep new value only (no change needed, already in row_data)
                applied_strategies[metric] = "keep"
            elif strategy in ("add", "sum"):
                # Cumulative: new + previous
                row_data[metric] = new_val + prev_val
                applied_strategies[metric] = f"add ({prev_val} + {new_val})"
            else:  # subtract (default)
                # Delta: new - previous
                row_data[metric] = new_val - prev_val
                applied_strategies[metric] = f"subtract ({new_val} - {prev_val})"

        if applied_strategies:
            logger.debug(
                "Applied deduplication strategies to duplicate metrics",
                strategies=applied_strategies,
                default_strategy=default_strategy,
            )

        return row_data

    async def _upsert_document_with_dedup_tracking(
        self,
        row_data: dict,
        identifier_column: str | None,
        dedup_service: DeduplicationService,
        run_id: UUID,
    ) -> str:
        """Upsert document and record deduplication tracking.

        Args:
            row_data: Row data to upsert
            task_schema_mapping: Optional schema mapping with identifier column
            dedup_service: Deduplication service for tracking
            run_id: Current run ID

        Returns:
            Result string: 'inserted', 'appended', or 'skipped'
        """
        # Call the standard upsert method
        result = await self._upsert_document(row_data, identifier_column)

        # Record deduplication event if we have the necessary metadata
        row_number = row_data.get("row_number", 0)
        identifier_value = row_data.get(identifier_column) if identifier_column else None

        if identifier_value:
            # Determine the dedup action based on result
            if result == "inserted":
                # New content, first occurrence
                await dedup_service.record_dedup_action(
                    run_id=run_id,
                    row_number=row_number,
                    identifier=str(identifier_value),
                    action="first_occurrence",
                    calculation_summary=None,
                )
            elif result == "appended":
                # Duplicate found, metrics changed (delta calculated)
                calculation_summary = {
                    "metric_deltas": row_data.get("metric_deltas"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                await dedup_service.record_dedup_action(
                    run_id=run_id,
                    row_number=row_number,
                    identifier=str(identifier_value),
                    action="inserted_delta",
                    calculation_summary=calculation_summary,
                )
            elif result == "skipped":
                # Duplicate found, no metrics changed
                await dedup_service.record_dedup_action(
                    run_id=run_id,
                    row_number=row_number,
                    identifier=str(identifier_value),
                    action="skipped",
                    calculation_summary=None,
                )

        return result

    async def ingest_task(
        self,
        task_id: UUID,
        run_id: UUID,
        file_bytes: bytes | None = None,
        webhook_payload: dict | None = None,
    ) -> IngestResult:
        """Ingest data for a task-based ingestion run.

        Dispatches based on task's adaptor_type and uses schema mappings if available.

        Args:
            task_id: UUID of the ingestion task.
            run_id: UUID of the task run.
            file_bytes: Optional file data for manual uploads.
            webhook_payload: Optional webhook payload for webhook adaptors.

        Returns:
            Ingestion result with counts and errors.
        """
        logger.info("Starting task-based ingestion", task_id=task_id, run_id=run_id)

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors: list[RowError] = []

        try:
            # Get task
            stmt = select(IngestionTask).where(IngestionTask.id == task_id)
            result = await self.db.execute(stmt)
            task = result.scalar_one_or_none()
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            # Note: Capture ORM attributes in individual async methods to avoid lazy-loading
            # Each ingestion method (_ingest_from_gmail_task, etc.) captures needed attributes
            task_adaptor_type = task.adaptor_type
            task_dedup_enabled = task.deduplication_enabled

            # Get schema mapping
            schema_service = SchemaMappingService(self.db)
            task_mapping = await schema_service.get_task_mapping(str(task_id))
            field_mappings = task_mapping.field_mappings if task_mapping else {}
            # Capture identifier_column early to prevent lazy-loading in other async contexts
            identifier_column = task_mapping.identifier_column if task_mapping else None

            # Initialize deduplication service if deduplication is enabled
            dedup_service = None
            if task_dedup_enabled is not None:
                from app.services.deduplication_service import get_deduplication_service
                dedup_service = await get_deduplication_service(self.db, task_id)

            logger.info("Task loaded", adaptor_type=task_adaptor_type, has_mapping=task_mapping is not None,
                       deduplication_enabled=task_dedup_enabled)

            if await self._is_run_stop_requested(run_id):
                raise IngestionCanceledError()

            # Dispatch based on adaptor type
            if task_adaptor_type == "gmail":
                # Gmail adaptor: fetch from Gmail
                rows_inserted, rows_updated, rows_failed, errors = await self._ingest_from_gmail_task(
                    task, run_id, field_mappings, identifier_column, dedup_service
                )

            elif task_adaptor_type == "webhook":
                # Webhook adaptor: process provided payload
                if not webhook_payload:
                    raise ValueError("webhook_payload required for webhook adaptor")
                rows_inserted, rows_updated, rows_failed, errors = await self._ingest_from_webhook(
                    task, run_id, webhook_payload, field_mappings, identifier_column, dedup_service
                )

            elif task_adaptor_type == "manual":
                # Manual adaptor: ingest from file
                if not file_bytes:
                    raise ValueError("file_bytes required for manual adaptor")
                rows_inserted, rows_updated, rows_failed, errors = await self._ingest_from_file_task(
                    task, run_id, file_bytes, field_mappings, identifier_column, dedup_service
                )

            else:
                raise ValueError(f"Unknown adaptor type: {task_adaptor_type}")

            # Update run with deduplication statistics if available
            if dedup_service:
                try:
                    dedup_summary = await dedup_service.get_deduplication_summary(run_id)
                    stmt = (
                        update(IngestionTaskRun)
                        .where(IngestionTaskRun.id == run_id)
                        .values(
                            total_rows_processed=dedup_summary.get("total_rows_processed", rows_inserted + rows_updated),
                            total_duplicates_found=dedup_summary.get("total_duplicates_found", 0),
                            total_deltas_calculated=dedup_summary.get("total_deltas_calculated", 0),
                            deduplication_enabled=True,
                        )
                    )
                    await self.db.execute(stmt)
                    await self.db.commit()
                except Exception as e:
                    logger.warning("Failed to update dedup statistics", error=str(e))

            # Trigger summary recomputation
            if rows_inserted > 0 or rows_updated > 0:
                try:
                    summary_service = get_summary_service(self.db)
                    await summary_service.compute_daily_summaries()
                except Exception as e:
                    logger.warning("Summary computation failed", error=str(e))

            logger.info(
                "Task-based ingestion complete",
                task_id=task_id,
                inserted=rows_inserted,
                updated=rows_updated,
                failed=rows_failed,
            )

            return IngestResult(
                rows_inserted=rows_inserted,
                rows_updated=rows_updated,
                rows_failed=rows_failed,
                errors=errors,
            )

        except IngestionCanceledError:
            logger.info("Task-based ingestion canceled", task_id=task_id, run_id=run_id)
            raise
        except Exception as e:
            logger.error("Task-based ingestion failed", error=str(e), task_id=task_id)
            raise

    async def _process_single_email(
        self,
        email: dict,
        task_id: UUID,
        run_id: UUID,
        field_mappings: dict,
        identifier_column: str | None,
        dedup_service: DeduplicationService | None,
        gmail_adapter: GmailAdapter,
        sheet_name: str = "Sheet1",
        gmail_source_type: str = "attachment",
    ) -> EmailProcessingResult:
        """Process a single email with per-email error handling.

        This method extracts one email's files, parses rows, and upserts documents.
        Errors are caught and classified for retry determination.

        Args:
            email: Email dict from gmail_adapter.fetch_data()
            task_id: Ingestion task ID
            run_id: Current run ID
            field_mappings: Schema field mappings
            identifier_column: Optional identifier column for deduplication
            dedup_service: Optional deduplication service
            gmail_adapter: Connected Gmail adapter for file extraction
            sheet_name: Excel sheet name to parse
            gmail_source_type: "attachment" or "download_link"

        Returns:
            EmailProcessingResult with outcome classification and error details
        """
        email_message_id = email.get("message_id", "")
        email_subject = email.get("subject", "")
        email_sender = email.get("from", "")

        # Initialize result object
        result = EmailProcessingResult(
            message_id=email_message_id,
            subject=email_subject,
            sender=email_sender,
        )

        try:
            # Skip already-processed emails
            if email_message_id and await self._is_email_processed(email_message_id):
                logger.info(
                    "Skipping already-processed email",
                    message_id=email_message_id,
                    subject=email_subject,
                )
                result.is_success = True
                return result

            logger.info("Processing Gmail email", subject=email_subject)

            # Extract files from email
            try:
                if gmail_source_type == "download_link":
                    file_items = await self._download_files_from_links(
                        run_id,
                        email.get("download_links", []),
                        result.errors,
                    )
                else:
                    # Attachment mode
                    file_items = [
                        {"filename": a["filename"], "data": a["data"]}
                        for a in email.get("attachments", [])
                    ]
            except Exception as e:
                logger.error(
                    "Error extracting files from email",
                    message_id=email_message_id,
                    error=str(e),
                )
                result.error_type = "extraction_error"
                result.error_message = str(e)
                result.is_success = False
                return result

            # Process each file in the email
            for file_item in file_items:
                if await self._is_run_stop_requested(run_id):
                    raise IngestionCanceledError(
                        result.rows_inserted, result.rows_updated, result.rows_failed
                    )

                filename = file_item["filename"]
                content_type = file_item.get("content_type", "")

                if not self._is_supported_report_file(filename, content_type):
                    logger.warning(
                        "Skipping unsupported file",
                        filename=filename,
                        content_type=content_type,
                    )
                    continue

                # Parse file rows
                try:
                    doc_rows, parse_errors = ExcelProcessor.parse_tabular_rows(
                        file_item["data"],
                        filename=filename,
                        sheet_name=sheet_name,
                    )
                except Exception as e:
                    logger.error(
                        "Error parsing file",
                        filename=filename,
                        message_id=email_message_id,
                        error=str(e),
                    )
                    result.error_type = "file_error"
                    result.error_message = f"Failed to parse {filename}: {str(e)}"
                    result.is_success = False
                    continue

                result.errors.extend(parse_errors)
                result.rows_failed += len(parse_errors)

                # Process each row from the file
                for row_data in doc_rows:
                    if await self._is_run_stop_requested(run_id):
                        raise IngestionCanceledError(
                            result.rows_inserted, result.rows_updated, result.rows_failed
                        )

                    try:
                        document_row = self._build_document_payload(row_data, field_mappings)

                        # Upsert with dedup tracking if available
                        if dedup_service:
                            upsert_result = await self._upsert_document_with_dedup_tracking(
                                document_row, identifier_column, dedup_service, run_id
                            )
                        else:
                            upsert_result = await self._upsert_document(
                                document_row, identifier_column
                            )

                        if upsert_result == "inserted":
                            result.rows_inserted += 1
                        elif upsert_result == "skipped":
                            result.rows_skipped += 1
                        else:  # updated
                            result.rows_updated += 1

                    except Exception as e:
                        import traceback

                        logger.error(
                            "Error upserting document from Gmail",
                            message_id=email_message_id,
                            error=str(e),
                            traceback=traceback.format_exc(),
                        )
                        result.errors.append(
                            {
                                "row_number": row_data.get("row_number", 0),
                                "error": f"Database error: {str(e)}",
                            }
                        )
                        result.rows_failed += 1
                        result.error_type = "row_error"

            # Determine overall success classification
            # Success: at least some rows inserted/updated, or 0 rows with no errors
            if result.rows_inserted > 0 or result.rows_updated > 0:
                result.is_success = True
                result.has_partial_success = True
            elif result.rows_failed > 0:
                result.is_success = False
            else:
                # 0 rows processed, no errors
                result.is_success = True

            return result

        except IngestionCanceledError:
            logger.info(
                "Email processing canceled",
                message_id=email_message_id,
                run_id=run_id,
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error processing email",
                message_id=email_message_id,
                error=str(e),
            )
            result.error_type = "row_error"
            result.error_message = f"Unexpected error: {str(e)}"
            result.is_success = False
            return result

    async def _ingest_from_gmail_task(
        self,
        task: IngestionTask,
        run_id: UUID,
        field_mappings: dict,
        identifier_column: str | None = None,
        dedup_service: DeduplicationService | None = None,
    ) -> tuple:
        """Ingest from Gmail using task configuration.

        Returns:
            Tuple of (rows_inserted, rows_updated, rows_failed, errors).
        """
        # Capture ORM attributes immediately to avoid lazy-loading in async context
        task_id = task.id
        adaptor_config = dict(task.adaptor_config or {})
        logger.info("Ingesting from Gmail task", task_id=task_id)

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors: list[RowError] = []

        gmail_adapter = None
        try:
            task_config = adaptor_config

            # Use task's adaptor config
            gmail_query = task_config.get("gmail_query", "")
            sheet_name = task_config.get("sheet_name", "Sheet1")
            sender_filter = task_config.get("sender_filter")
            subject_pattern = task_config.get("subject_pattern")
            oauth_config = dict(task_config.get("gmail_oauth", {}))
            gmail_source_type = task_config.get("gmail_source_type", "attachment")
            download_link_regex = task_config.get("download_link_regex") or r"https?://\S+"

            # Backfill task-scoped OAuth config from app settings so older linked tasks
            # continue working after the client_secret persistence fix.
            oauth_changed = False
            if not oauth_config.get("client_id") and settings.gmail_oauth_client_id:
                oauth_config["client_id"] = settings.gmail_oauth_client_id
                oauth_changed = True
            if not oauth_config.get("client_secret") and settings.gmail_oauth_client_secret:
                oauth_config["client_secret"] = settings.gmail_oauth_client_secret
                oauth_changed = True
            if not oauth_config.get("token_uri") and settings.gmail_oauth_token_uri:
                oauth_config["token_uri"] = settings.gmail_oauth_token_uri
                oauth_changed = True

            # Connect to Gmail
            # Initialize credential service for tracking
            credential_service = get_gmail_credential_service(self.db)

            # Create adapter with credential service integration
            gmail_adapter = GmailAdapter(
                oauth_config=oauth_config,
                credential_service=credential_service,
                task_id=str(task.id),
            )
            # Connect to Gmail with error handling
            try:
                await gmail_adapter.connect()
            except CredentialExpiredError as e:
                # Permanent auth failure: refresh token is invalid
                logger.error(
                    "Gmail credential expired (invalid_grant)",
                    task_id=task.id,
                    error=str(e),
                )

                # Mark run as auth error
                stmt = (
                    update(IngestionTaskRun)
                    .where(IngestionTaskRun.id == run_id)
                    .values(
                        error_type="auth_error",
                        error_code="invalid_grant",
                        status=RunStatus.FAILED,
                        completed_at=datetime.utcnow(),
                        error_message=str(e),
                    )
                )
                await self.db.execute(stmt)
                await self.db.commit()

                return 0, 0, 1, [RowError(row_number=0, error=str(e))]

            except TemporaryAuthError as e:
                # Transient auth failure
                logger.warning(
                    "Gmail authentication temporary failure",
                    task_id=task.id,
                    error=str(e),
                )

                # Mark run as auth error but allow retry
                stmt = (
                    update(IngestionTaskRun)
                    .where(IngestionTaskRun.id == run_id)
                    .values(
                        error_type="auth_error",
                        error_code="temporary_auth_failure",
                        status=RunStatus.FAILED,
                        completed_at=datetime.utcnow(),
                        error_message=str(e),
                    )
                )
                await self.db.execute(stmt)
                await self.db.commit()

                return 0, 0, 1, [RowError(row_number=0, error=str(e))]


            # Persist refreshed token state, if changed.
            # Note: Cannot persist task.adaptor_config in async context due to greenlet constraints
            # The adapted config will be updated on next task run via task_config initialization
            refreshed_oauth = gmail_adapter.get_oauth_config()
            if refreshed_oauth or oauth_changed:
                logger.debug("Gmail OAuth config updated but not persisted in async context",
                           oauth_changed=oauth_changed)

            # Fetch emails
            emails = await gmail_adapter.fetch_data(
                query=gmail_query,
                sender_filter=sender_filter,
                subject_pattern=subject_pattern,
                max_results=task_config.get("max_results", 25),
                source_type=gmail_source_type,
                link_regex=download_link_regex,
                allowed_extensions=task_config.get("allowed_extensions"),  # e.g., ['xlsx', 'csv']
            )

            # Process each email
            for email in emails:
                if await self._is_run_stop_requested(run_id):
                    raise IngestionCanceledError(rows_inserted, rows_updated, rows_failed)

                email_message_id = email.get("message_id", "")
                email_subject = email.get("subject", "")
                email_sender = email.get("from", "")

                try:
                    # Per-email savepoint: isolate this email's processing
                    async with self.db.begin_nested():
                        # Process single email with error classification
                        email_result = await self._process_single_email(
                            email=email,
                            task_id=task_id,
                            run_id=run_id,
                            field_mappings=field_mappings,
                            identifier_column=identifier_column,
                            dedup_service=dedup_service,
                            gmail_adapter=gmail_adapter,
                            sheet_name=sheet_name,
                            gmail_source_type=gmail_source_type,
                        )

                        # Accumulate results
                        rows_inserted += email_result.rows_inserted
                        rows_updated += email_result.rows_updated
                        rows_failed += email_result.rows_failed
                        errors.extend(
                            [
                                RowError(
                                    row_number=e.get("row_number", 0),
                                    error=e.get("error", "Unknown error"),
                                )
                                for e in email_result.errors
                            ]
                        )

                        # Record email processing outcome
                        if email_message_id:
                            # Determine email success and retry status
                            is_email_success = email_result.is_success
                            is_email_retryable = email_result.is_retryable

                            await self._record_processed_email(
                                message_id=email_message_id,
                                subject=email_subject,
                                sender=email_sender,
                                task_id=task_id,
                                rows_inserted=email_result.rows_inserted,
                                rows_updated=email_result.rows_updated,
                                rows_skipped=email_result.rows_skipped,
                                rows_failed=email_result.rows_failed,
                                is_success=is_email_success,
                                is_retryable=is_email_retryable,
                            )

                            # Try to remove UNREAD label
                            try:
                                gmail_service = gmail_adapter.service
                                if gmail_service is not None:
                                    await gmail_service.users().messages().modify(
                                        userId="me",
                                        id=email_message_id,
                                        body={"removeLabelIds": ["UNREAD"]},
                                    ).execute()
                            except Exception as e:
                                logger.warning(
                                    "Could not mark email as processed",
                                    message_id=email_message_id,
                                    error=str(e),
                                )

                except Exception as e:
                    # Email processing failed (extraction error, etc.)
                    logger.error(
                        "Failed to process email in transaction",
                        message_id=email_message_id,
                        error=str(e),
                    )
                    rows_failed += 1
                    errors.append(RowError(row_number=0, error=f"Email processing error: {str(e)}"))
                    # Continue to next email - one email failure doesn't block others
                    continue

        except IngestionCanceledError:
            logger.info("Gmail task ingestion canceled", task_id=task_id, run_id=run_id)
            raise
        except Exception as e:
            logger.error("Gmail task ingestion failed", error=str(e), task_id=task_id)
            rows_failed += 1
            errors.append(RowError(row_number=0, error=f"Gmail adapter error: {e!s}"))
        finally:
            if gmail_adapter is not None:
                try:
                    await gmail_adapter.disconnect()
                except Exception as disconnect_error:
                    logger.warning("Failed to disconnect Gmail adapter", error=str(disconnect_error))

        return rows_inserted, rows_updated, rows_failed, errors

    @staticmethod
    def _is_supported_report_file(filename: str, content_type: str) -> bool:
        """Check whether a downloaded file looks like an Excel or CSV report."""
        normalized_name = (filename or "").lower()
        normalized_type = (content_type or "").lower()
        if normalized_name.endswith((".xlsx", ".xls", ".csv")):
            return True
        return any(
            marker in normalized_type
            for marker in [
                "spreadsheetml",
                "ms-excel",
                "text/csv",
                "application/csv",
                "octet-stream",
            ]
        )

    async def _download_files_from_links(
        self,
        run_id: UUID,
        urls: list[str],
        errors: list[RowError],
    ) -> list[dict]:
        """Download files from a list of URLs and return as file items.

        Args:
            urls: List of download URLs.
            errors: Error list to append failures to (mutated in place).

        Returns:
            List of dicts with 'filename' and 'data' keys.
        """
        file_items = []
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=float(settings.http_client_timeout_seconds),
        ) as client:
            for url in urls:
                if await self._is_run_stop_requested(run_id):
                    raise IngestionCanceledError()
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    file_data = resp.content
                    content_type = resp.headers.get("content-type", "")

                    # Infer filename from Content-Disposition header or URL path
                    filename = ""
                    content_disp = resp.headers.get("content-disposition", "")
                    if "filename=" in content_disp:
                        filename = content_disp.split("filename=")[-1].strip().strip('"\'')
                    if not filename:
                        filename = url.split("?")[0].rstrip("/").split("/")[-1] or "report.xlsx"

                    if "." not in filename:
                        if "csv" in content_type.lower():
                            filename = f"{filename}.csv"
                        elif any(marker in content_type.lower() for marker in ["spreadsheetml", "ms-excel", "octet-stream"]):
                            filename = f"{filename}.xlsx"

                    logger.info(
                        "Downloaded file from link",
                        url=url,
                        filename=filename,
                        content_type=content_type,
                        size=len(file_data),
                    )
                    file_items.append({"filename": filename, "data": file_data, "content_type": content_type})

                except Exception as e:
                    logger.error("Failed to download file from URL", url=url, error=str(e))
                    errors.append(RowError(row_number=0, error=f"Download failed [{url}]: {e!s}"))

        return file_items

    async def _ingest_from_webhook(
        self,
        task: IngestionTask,
        run_id: UUID,
        payload: dict,
        field_mappings: dict,
        identifier_column: str | None = None,
        dedup_service: DeduplicationService | None = None,
    ) -> tuple:
        """Ingest from webhook payload.

        Returns:
            Tuple of (rows_inserted, rows_updated, rows_failed, errors).
        """
        logger.info("Ingesting from webhook", task_id=task.id)

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors = []

        try:
            # Transform payload to document rows
            # For now, assume payload is a dict or list that can be processed
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict):
                rows = [payload]
            else:
                raise ValueError("Webhook payload must be dict or list")

            for row_data in rows:
                if await self._is_run_stop_requested(run_id):
                    raise IngestionCanceledError(rows_inserted, rows_updated, rows_failed)

                try:
                    # Apply field mappings if provided
                    if field_mappings:
                        mapped_data = {}
                        for source, target in field_mappings.items():
                            source_column = self._source_key_to_column(source)
                            if source_column in row_data:
                                mapped_data[target] = row_data[source_column]
                        row_data = {**row_data, **mapped_data}

                    result = await self._upsert_document(row_data, identifier_column) if not dedup_service else await self._upsert_document_with_dedup_tracking(row_data, identifier_column, dedup_service, run_id)
                    if result == "inserted":
                        rows_inserted += 1
                    elif result == "updated":
                        rows_updated += 1

                except Exception as e:
                    logger.error("Error upserting webhook document", error=str(e))
                    errors.append(RowError(row_number=0, error=f"Database error: {e!s}"))
                    rows_failed += 1

        except IngestionCanceledError:
            logger.info("Webhook ingestion canceled", task_id=task.id, run_id=run_id)
            raise
        except Exception as e:
            logger.error("Webhook ingestion failed", error=str(e), task_id=task.id)
            errors.append(RowError(row_number=0, error=f"Webhook processing error: {e!s}"))

        return rows_inserted, rows_updated, rows_failed, errors

    async def _ingest_from_file_task(
        self,
        task: IngestionTask,
        run_id: UUID,
        file_data: bytes,
        field_mappings: dict,
        identifier_column: str | None = None,
        dedup_service: DeduplicationService | None = None,
    ) -> tuple:
        """Ingest from uploaded file using task configuration.

        Returns:
            Tuple of (rows_inserted, rows_updated, rows_failed, errors).
        """
        # Capture ORM attributes immediately to avoid lazy-loading in async context
        task_id = task.id
        adaptor_config = dict(task.adaptor_config or {})
        logger.info("Ingesting from file via task", task_id=task_id)

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors = []

        try:
            task_config = adaptor_config
            sheet_name = task_config.get("sheet_name", "Sheet1")

            filename = task_config.get("uploaded_filename", "uploaded.xlsx")

            # Parse file preserving raw source columns, then apply task mapping.
            doc_rows, parse_errors = ExcelProcessor.parse_tabular_rows(file_data, filename=filename, sheet_name=sheet_name)

            errors.extend(parse_errors)
            rows_failed = len(parse_errors)

            # Upsert rows
            for row_data in doc_rows:
                if await self._is_run_stop_requested(run_id):
                    raise IngestionCanceledError(rows_inserted, rows_updated, rows_failed)

                try:
                    document_row = self._build_document_payload(row_data, field_mappings)
                    if dedup_service:
                        result = await self._upsert_document_with_dedup_tracking(
                            document_row, identifier_column, dedup_service, run_id
                        )
                    else:
                        result = await self._upsert_document(document_row, identifier_column)
                    if result == "inserted":
                        rows_inserted += 1
                    elif result == "updated":
                        rows_updated += 1

                except Exception as e:
                    logger.error("Error upserting file document", error=str(e))
                    errors.append(RowError(row_number=row_data.get("row_number", 0), error=f"Database error: {e!s}"))
                    rows_failed += 1

        except IngestionCanceledError:
            logger.info("File task ingestion canceled", task_id=task.id, run_id=run_id)
            raise
        except Exception as e:
            logger.error("File task ingestion failed", error=str(e), task_id=task.id)
            errors.append(RowError(row_number=0, error=f"File processing error: {e!s}"))

        return rows_inserted, rows_updated, rows_failed, errors


def get_ingestion_service(db_session: AsyncSession) -> IngestionService:
    """Factory for ingestion service."""
    return IngestionService(db_session)
