# Gmail Refactoring - Exact File Changes

## File: backend/src/app/services/ingestion_service.py

---

## CHANGE 1: Update _record_processed_email() Signature (Lines 324-351)

### LOCATION
File: `backend/src/app/services/ingestion_service.py`
Lines: 324-351

### BEFORE (34 lines)
```python
    async def _record_processed_email(
        self,
        message_id: str,
        subject: str | None = None,
        sender: str | None = None,
        task_id: UUID | None = None,
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
                processed_at=func.now(),
            )
            .on_conflict_do_nothing(index_elements=["message_id"])
        )
        await self.db.execute(stmt)
```

### AFTER (42 lines)
```python
    async def _record_processed_email(
        self,
        message_id: str,
        subject: str | None = None,
        sender: str | None = None,
        task_id: UUID | None = None,
        rows_inserted: int = 0,
        rows_skipped: int = 0,
        rows_failed: int = 0,
        rows_updated: int = 0,
        is_success: bool = True,
        is_retryable: bool = False,
    ) -> None:
        """Persist a ProcessedEmail record with success/retry classification.

        Tracks whether email should be queued for retry based on error classification.
        Silently ignores duplicate inserts.

        Args:
            message_id: Gmail message ID (unique per message)
            subject: Email subject for audit trail
            sender: Email sender for audit trail
            task_id: ID of ingestion task that processed this email
            rows_inserted: Count of new documents inserted
            rows_updated: Count of existing documents updated
            rows_skipped: Count of rows skipped (no mapped fields)
            rows_failed: Count of rows that failed to insert/update
            is_success: Whether email was processed without critical errors
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
```

### DIFFS
- Add 3 new parameters: `rows_updated`, `is_success`, `is_retryable`
- Expand docstring with 16 new lines explaining parameters
- Add 3 new fields to `.values()` statement

---

## CHANGE 2: Add New Method (Insert Before Line 1055)

### LOCATION
File: `backend/src/app/services/ingestion_service.py`
Insert new method before `_ingest_from_gmail_task()` at line 1055

### METHOD: _process_single_email()

**Full implementation provided in IMPLEMENTATION_PLAN_GMAIL_REFACTORING.md Part 2**

**Summary:**
- 230+ line method
- Processes single email with error isolation
- Returns EmailProcessingResult
- Handles: already processed check, file extraction, parsing, upsert
- Error classification: extraction_error, file_error, row_error
- Success classification: is_success, is_retryable, has_partial_success

---

## CHANGE 3: Refactor Email Processing Loop (Lines 1188-1297)

### LOCATION
File: `backend/src/app/services/ingestion_service.py`
Lines: 1188-1297 (entire email processing loop in _ingest_from_gmail_task)

### BEFORE (110 lines)
```python
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
                            if dedup_service:
                                result = await self._upsert_document_with_dedup_tracking(
                                    document_row, identifier_column, dedup_service, run_id
                                )
                            else:
                                result = await self._upsert_document(document_row, identifier_column)
                            if result == "inserted":
                                rows_inserted += 1
                                email_inserted += 1
                            elif result == "skipped":
                                email_skipped += 1
                            else:
                                rows_updated += 1
                                email_inserted += 1

                        except Exception as e:
                            import traceback
                            logger.error("Error upserting document from Gmail", error=str(e), traceback=traceback.format_exc())
                            errors.append(
                                RowError(row_number=row_data.get("row_number", 0), error=f"Database error: {e!s}")
                            )
                            rows_failed += 1
                            email_failed += 1

                # Record email as processed in DB and remove UNREAD label
                if email_message_id:
                    await self._record_processed_email(
                        message_id=email_message_id,
                        subject=email_subject,
                        sender=email_sender,
                        task_id=task_id,
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
```

### AFTER (120+ lines with per-email savepoint and retry queueing)

**Full implementation provided in IMPLEMENTATION_PLAN_GMAIL_REFACTORING.md Part 3**

**Key changes:**
1. Add FailedEmailService initialization (5 lines)
2. Wrap email processing in `async with self.db.begin_nested():` savepoint
3. Call `_process_single_email()` method instead of inline logic
4. Record processed email with new `is_success`, `is_retryable` fields
5. Queue failed emails for retry using FailedEmailService
6. Handle unexpected exceptions per-email instead of failing entire run
7. Only remove UNREAD label if rows were successfully processed

---

## CHANGE 4: Add Import at Top of File

### LOCATION
File: `backend/src/app/services/ingestion_service.py`
Lines: 1-40 (import section)

### ADD IMPORT
```python
import traceback  # For detailed error logging in exception handlers
```

### Verify These Are Already Imported
```python
from app.services.email_processing_result import EmailProcessingResult  # Verify exists
from app.services.failed_email_service import FailedEmailService  # Lazy import in method (OK)
```

---

## Summary of Changes

| Item | Type | Lines | Status |
|------|------|-------|--------|
| _record_processed_email() | Update | 324-351 | +8 lines (parameters & docstring) |
| _process_single_email() | New | ~1050-1280 | +230 lines (new method) |
| Email processing loop | Replace | 1188-1297 | ~120 lines (refactored) |
| Imports | Add | Top of file | +1 line (traceback) |
| **TOTAL** | | | **~350 new lines, 110 removed = 240 net additions** |

---

## File Size Impact

- **Before**: ~1313 lines
- **After**: ~1553 lines (+240 lines / +18%)
- **Reasoning**: New method extracted, more detailed error handling, per-email transaction logic

---

## Testing After Changes

### Unit Tests to Add
```python
# backend/tests/test_ingestion_service.py

def test_process_single_email_already_processed():
    """Should skip email already in ProcessedEmail table."""

def test_process_single_email_no_files():
    """Should return success if email has no files."""

def test_process_single_email_parse_error():
    """Should classify parse errors as retryable."""

def test_process_single_email_all_rows_succeeded():
    """Should mark as success with no retry."""

def test_process_single_email_partial_success():
    """Should mark as success even with some row failures."""

def test_process_single_email_all_rows_failed():
    """Should mark as retryable if all rows failed."""

def test_ingest_gmail_per_email_savepoint():
    """Should isolate email failure to that email only."""

def test_ingest_gmail_queue_failed_email():
    """Should queue failed emails in FailedEmailQueue."""

def test_ingest_gmail_continue_after_email_failure():
    """Should continue processing next email after failure."""
```

### Integration Test
```python
def test_ingest_gmail_task_partial_failure():
    """3 emails: 2 succeed, 1 fails. Run should complete with partial stats."""
    # Setup 3 mock emails with different outcomes
    # Run ingestion
    # Verify: rows_inserted=X, rows_updated=Y, rows_failed=Z
    # Verify: 1 email in FailedEmailQueue
    # Verify: 3 emails in ProcessedEmail with correct is_success flags
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] All existing tests pass
- [ ] New unit tests pass
- [ ] Integration tests pass
- [ ] Code review approved
- [ ] Linting clean: `ruff check backend/src/app/services/ingestion_service.py`
- [ ] Formatting clean: `ruff format backend/src/app/services/ingestion_service.py`

### Deployment
- [ ] Deploy code to staging
- [ ] Verify celery worker starts without errors
- [ ] Run manual test with Gmail task
- [ ] Check ProcessedEmail records have new fields
- [ ] Intentionally fail an email and verify FailedEmailQueue entry

### Post-Deployment (Production)
- [ ] Monitor logs for exceptions in first 30 minutes
- [ ] Verify at least one successful Gmail ingest run
- [ ] Check ProcessedEmail table has proper is_success/is_retryable values
- [ ] Verify no regressions in ingestion success rate

---

## Risk Assessment

### Low Risk
- ✓ New method is self-contained
- ✓ Existing logic moved, not changed
- ✓ Error handling improved
- ✓ Tests can be added without affecting existing code

### Medium Risk
- ⚠ Savepoint behavior differs by database
- ⚠ FailedEmailService availability handled gracefully
- ⚠ More complex error flow (more edge cases)

### Mitigation
- Test thoroughly on staging first
- Gradual rollout: stage first, then production
- Monitor error rates closely after deployment
- Have rollback plan (can revert to previous version)

---

## Rollback Plan

If issues arise in production:

### Option 1: Quick Rollback (< 5 min downtime)
1. Revert commit to previous version
2. Restart API and celery workers
3. Run migrations backward (if schema changed)
4. Verify ingestion working again

### Option 2: Graceful Rollback (no downtime)
1. Deploy previous version with feature flag
2. Disable new per-email savepoint logic
3. Run fallback to old inline loop
4. Gradually migrate back over time

### Data Safety
- ✓ ProcessedEmail already has new columns (migration 020)
- ✓ FailedEmailQueue already exists (migration 022)
- ✓ No data loss if rolling back
- ✓ Ingestion run data not affected by code version

