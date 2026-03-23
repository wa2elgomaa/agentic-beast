"""Service for orchestrating data ingestion pipeline."""

from datetime import date, datetime, time
from typing import List, Optional
from uuid import UUID
import hashlib
import json

import httpx
from sqlalchemy import and_, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gmail_adapter import GmailAdapter
from app.config import settings
from app.logging import get_logger
from app.models import Document, IngestionTask, IngestionTaskRun, ProcessedEmail, RunStatus
from app.processors.excel_processor import ExcelProcessor
from app.schemas.ingestion import IngestResult, RowError
from app.services.embedding_service import get_embedding_service
from app.services.summary_service import get_summary_service
from app.services.schema_mapping_service import SchemaMappingService
from app.services.file_storage_service import get_file_storage_service

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
    def _coerce_reported_time(reported_time_value: Optional[object]) -> Optional[time]:
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
        if "reported_time" in mapped_data and mapped_data["reported_time"]:
            # Already mapped from source
            reported_time_value = self._coerce_reported_time(mapped_data["reported_time"])
        elif "reported_at" in source_row and source_row["reported_at"]:
            # Try to extract time from reported_at
            reported_time_value = self._coerce_reported_time(source_row["reported_at"])
        if not reported_time_value:
            # Fallback to current ingestion time
            reported_time_value = datetime.now().time()

        payload = {
            "sheet_name": source_row.get("sheet_name", "Sheet1"),
            "row_number": source_row.get("row_number", 0),
            "text": str(text_value),
            "reported_time": reported_time_value,
            "doc_metadata": {"source_row": source_metadata},
        }
        payload.update(mapped_data)
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
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        task_id: Optional[UUID] = None,
        rows_inserted: int = 0,
        rows_skipped: int = 0,
        rows_failed: int = 0,
    ) -> None:
        """Persist a ProcessedEmail record. Silently ignores duplicate inserts."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(ProcessedEmail)
            .values(
                message_id=message_id,
                task_id=task_id,
                subject=subject,
                sender=sender,
                rows_inserted=rows_inserted,
                rows_skipped=rows_skipped,
                rows_failed=rows_failed,
            )
            .on_conflict_do_nothing(index_elements=["message_id"])
        )
        await self.db.execute(stmt)

    async def ingest_from_gmail(self) -> IngestResult:
        """Fetch and ingest data from Gmail attachments.

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
                            result = await self._upsert_document(row_data)
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
                                    error=f"Database error: {str(e)}",
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
            errors.append(RowError(row_number=0, error=f"Gmail adapter error: {str(e)}"))

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

    async def ingest_from_file(self, file_data: bytes, filename: str) -> IngestResult:
        """Ingest data from uploaded file.

        Args:
            file_data: Raw file bytes.
            filename: Original filename.

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
                    result = await self._upsert_document(row_data)
                    if result == "inserted":
                        rows_inserted += 1
                    elif result == "updated":
                        rows_updated += 1

                except Exception as e:
                    logger.error("Error upserting document", error=str(e))
                    errors.append(
                        RowError(
                            row_number=row_data.get("row_number", 0),
                            error=f"Database error: {str(e)}",
                        )
                    )
                    rows_failed += 1

        except Exception as e:
            logger.error("File ingestion failed", error=str(e))
            errors.append(RowError(row_number=0, error=f"File processing error: {str(e)}"))

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

    async def _upsert_document(self, row_data: dict) -> str:
        """Insert or append document record with full history tracking.

        Implements append-only history: instead of updating, creates new row
        if metrics have changed. Marks old record as stale (is_current=FALSE).

        Args:
            row_data: Row data dict.

        Returns:
            'inserted' (new record), 'appended' (metrics changed), or 'skipped' (no change).
        """
        # Ensure is_current defaults to FALSE if not set
        if "is_current" not in row_data:
            row_data["is_current"] = True

        # Check if record exists (by sheet_name and row_number, latest version only)
        stmt = select(Document).where(
            and_(
                Document.sheet_name == row_data.get("sheet_name"),
                Document.row_number == row_data.get("row_number"),
                Document.is_current == True,
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

            # Metrics changed: mark old record as stale and insert new version
            logger.debug(
                "Document metrics changed, appending new version",
                row_number=row_data.get("row_number"),
                old_fingerprint=old_fingerprint,
                new_fingerprint=new_fingerprint,
            )
            stmt = (
                update(Document)
                .where(Document.id == existing.id)
                .values(is_current=False)
            )
            await self.db.execute(stmt)

            # Insert new version with is_current=TRUE
            stmt = insert(Document).values(**row_data)
            await self.db.execute(stmt)
            return "appended"
        else:
            # New record: insert with is_current=TRUE
            stmt = insert(Document).values(**row_data)
            await self.db.execute(stmt)
            logger.debug("Document inserted", row_number=row_data.get("row_number"))
            return "inserted"

    async def ingest_task(
        self,
        task_id: UUID,
        run_id: UUID,
        file_bytes: Optional[bytes] = None,
        webhook_payload: Optional[dict] = None,
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
        errors = []

        try:
            # Get task
            stmt = select(IngestionTask).where(IngestionTask.id == task_id)
            result = await self.db.execute(stmt)
            task = result.scalar_one_or_none()

            if not task:
                raise ValueError(f"Task not found: {task_id}")

            # Get schema mapping
            schema_service = SchemaMappingService(self.db)
            task_mapping = await schema_service.get_task_mapping(str(task_id))
            field_mappings = task_mapping.field_mappings if task_mapping else {}

            logger.info("Task loaded", adaptor_type=task.adaptor_type, has_mapping=task_mapping is not None)

            if await self._is_run_stop_requested(run_id):
                raise IngestionCanceledError()

            # Dispatch based on adaptor type
            if task.adaptor_type == "gmail":
                # Gmail adaptor: fetch from Gmail
                rows_inserted, rows_updated, rows_failed, errors = await self._ingest_from_gmail_task(
                    task, run_id, field_mappings
                )

            elif task.adaptor_type == "webhook":
                # Webhook adaptor: process provided payload
                if not webhook_payload:
                    raise ValueError("webhook_payload required for webhook adaptor")
                rows_inserted, rows_updated, rows_failed, errors = await self._ingest_from_webhook(
                    task, run_id, webhook_payload, field_mappings
                )

            elif task.adaptor_type == "manual":
                # Manual adaptor: ingest from file
                if not file_bytes:
                    raise ValueError("file_bytes required for manual adaptor")
                rows_inserted, rows_updated, rows_failed, errors = await self._ingest_from_file_task(
                    task, run_id, file_bytes, field_mappings
                )

            else:
                raise ValueError(f"Unknown adaptor type: {task.adaptor_type}")

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

    async def _ingest_from_gmail_task(
        self,
        task: IngestionTask,
        run_id: UUID,
        field_mappings: dict,
    ) -> tuple:
        """Ingest from Gmail using task configuration.

        Returns:
            Tuple of (rows_inserted, rows_updated, rows_failed, errors).
        """
        logger.info("Ingesting from Gmail task", task_id=task.id)

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors = []

        gmail_adapter = None
        try:
            task_config = dict(task.adaptor_config or {})

            # Use task's adaptor config
            gmail_query = task_config.get("gmail_query", "has:attachment is:unread")
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
            gmail_adapter = GmailAdapter(oauth_config=oauth_config)
            await gmail_adapter.connect()

            # Persist refreshed token state, if changed.
            refreshed_oauth = gmail_adapter.get_oauth_config()
            if refreshed_oauth or oauth_changed:
                updated_config = dict(task.adaptor_config or {})
                updated_config["gmail_oauth"] = refreshed_oauth or oauth_config
                task.adaptor_config = updated_config
                self.db.add(task)

            # Fetch emails
            emails = await gmail_adapter.fetch_data(
                query=gmail_query,
                sender_filter=sender_filter,
                subject_pattern=subject_pattern,
                max_results=task_config.get("max_results", 25),
                source_type=gmail_source_type,
                link_regex=download_link_regex,
            )

            # Process each email
            for email in emails:
                if await self._is_run_stop_requested(run_id):
                    raise IngestionCanceledError(rows_inserted, rows_updated, rows_failed)

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

                logger.info("Processing Gmail email", subject=email_subject)
                email_inserted = 0
                email_skipped = 0
                email_failed = 0

                if gmail_source_type == "download_link":
                    file_items = await self._download_files_from_links(
                        run_id,
                        email.get("download_links", []),
                        errors,
                    )
                else:
                    file_items = [
                        {"filename": a["filename"], "data": a["data"]}
                        for a in email.get("attachments", [])
                    ]

                for file_item in file_items:
                    if await self._is_run_stop_requested(run_id):
                        raise IngestionCanceledError(rows_inserted, rows_updated, rows_failed)

                    filename = file_item["filename"]
                    content_type = file_item.get("content_type", "")
                    if not self._is_supported_report_file(filename, content_type):
                        logger.warning(
                            "Skipping unsupported downloaded file",
                            filename=filename,
                            content_type=content_type,
                        )
                        continue

                    # Parse document preserving raw source columns, then apply task mapping.
                    doc_rows, parse_errors = ExcelProcessor.parse_tabular_rows(
                        file_item["data"],
                        filename=filename,
                        sheet_name=sheet_name,
                    )

                    errors.extend(parse_errors)
                    rows_failed += len(parse_errors)

                    # Apply field mappings and upsert
                    for row_data in doc_rows:
                        if await self._is_run_stop_requested(run_id):
                            raise IngestionCanceledError(rows_inserted, rows_updated, rows_failed)

                        try:
                            document_row = self._build_document_payload(row_data, field_mappings)
                            result = await self._upsert_document(document_row)
                            if result == "inserted":
                                rows_inserted += 1
                                email_inserted += 1
                            elif result == "skipped":
                                email_skipped += 1
                            else:
                                rows_updated += 1
                                email_inserted += 1

                        except Exception as e:
                            logger.error("Error upserting document from Gmail", error=str(e))
                            errors.append(
                                RowError(row_number=row_data.get("row_number", 0), error=f"Database error: {str(e)}")
                            )
                            rows_failed += 1
                            email_failed += 1

                # Record email as processed in DB and remove UNREAD label
                if email_message_id:
                    await self._record_processed_email(
                        message_id=email_message_id,
                        subject=email_subject,
                        sender=email_sender,
                        task_id=task.id,
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

        except IngestionCanceledError:
            logger.info("Gmail task ingestion canceled", task_id=task.id, run_id=run_id)
            raise
        except Exception as e:
            logger.error("Gmail task ingestion failed", error=str(e), task_id=task.id)
            rows_failed += 1
            errors.append(RowError(row_number=0, error=f"Gmail adapter error: {str(e)}"))
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
        urls: List[str],
        errors: List[RowError],
    ) -> List[dict]:
        """Download files from a list of URLs and return as file items.

        Args:
            urls: List of download URLs.
            errors: Error list to append failures to (mutated in place).

        Returns:
            List of dicts with 'filename' and 'data' keys.
        """
        file_items = []
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
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
                    errors.append(RowError(row_number=0, error=f"Download failed [{url}]: {str(e)}"))

        return file_items

    async def _ingest_from_webhook(
        self,
        task: IngestionTask,
        run_id: UUID,
        payload: dict,
        field_mappings: dict,
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

                    result = await self._upsert_document(row_data)
                    if result == "inserted":
                        rows_inserted += 1
                    elif result == "updated":
                        rows_updated += 1

                except Exception as e:
                    logger.error("Error upserting webhook document", error=str(e))
                    errors.append(RowError(row_number=0, error=f"Database error: {str(e)}"))
                    rows_failed += 1

        except IngestionCanceledError:
            logger.info("Webhook ingestion canceled", task_id=task.id, run_id=run_id)
            raise
        except Exception as e:
            logger.error("Webhook ingestion failed", error=str(e), task_id=task.id)
            errors.append(RowError(row_number=0, error=f"Webhook processing error: {str(e)}"))

        return rows_inserted, rows_updated, rows_failed, errors

    async def _ingest_from_file_task(
        self,
        task: IngestionTask,
        run_id: UUID,
        file_data: bytes,
        field_mappings: dict,
    ) -> tuple:
        """Ingest from uploaded file using task configuration.

        Returns:
            Tuple of (rows_inserted, rows_updated, rows_failed, errors).
        """
        logger.info("Ingesting from file via task", task_id=task.id)

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors = []

        try:
            task_config = dict(task.adaptor_config or {})
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
                    result = await self._upsert_document(document_row)
                    if result == "inserted":
                        rows_inserted += 1
                    elif result == "updated":
                        rows_updated += 1

                except Exception as e:
                    logger.error("Error upserting file document", error=str(e))
                    errors.append(RowError(row_number=row_data.get("row_number", 0), error=f"Database error: {str(e)}"))
                    rows_failed += 1

        except IngestionCanceledError:
            logger.info("File task ingestion canceled", task_id=task.id, run_id=run_id)
            raise
        except Exception as e:
            logger.error("File task ingestion failed", error=str(e), task_id=task.id)
            errors.append(RowError(row_number=0, error=f"File processing error: {str(e)}"))

        return rows_inserted, rows_updated, rows_failed, errors


def get_ingestion_service(db_session: AsyncSession) -> IngestionService:
    """Factory for ingestion service."""
    return IngestionService(db_session)
