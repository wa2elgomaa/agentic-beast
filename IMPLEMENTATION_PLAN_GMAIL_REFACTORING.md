# Gmail Email Ingestion Refactoring - Implementation Plan

## Executive Summary

Refactor the `_ingest_from_gmail_task()` method in `backend/src/app/services/ingestion_service.py` to support per-email transaction handling and failed email retry. This enables isolation of failures to individual emails rather than failing the entire ingestion run.

**Current State:**
- All emails processed in implicit single transaction scope
- Single email failure fails entire run
- No differentiation between retryable and non-retryable failures

**New State:**
- Per-email savepoint (nested transaction) for error isolation
- Failed emails queued for retry with exponential backoff
- Partial success (some emails succeed, some fail) is valid outcome
- Each email gets `is_success` and `is_retryable` classification

---

## Part 1: Method Signature Updates

### 1a. Update `_record_processed_email()` Signature

**File:** `backend/src/app/services/ingestion_service.py` (lines 324-351)

**Current Signature:**
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
```

**New Signature:**
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
    rows_updated: int = 0,  # NEW: track updates separately
    is_success: bool = True,  # NEW: email processed without critical errors
    is_retryable: bool = False,  # NEW: should be queued for retry if failed
) -> None:
```

**Updated Implementation:**
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
            rows_updated=rows_updated,  # NEW
            rows_skipped=rows_skipped,
            rows_failed=rows_failed,
            is_success=is_success,  # NEW
            is_retryable=is_retryable,  # NEW
            processed_at=func.now(),
        )
        .on_conflict_do_nothing(index_elements=["message_id"])
    )
    await self.db.execute(stmt)
```

---

## Part 2: New `_process_single_email()` Method

### Create New Method

**File:** `backend/src/app/services/ingestion_service.py`

**Location:** Insert before `_ingest_from_gmail_task()` method (around line 1055)

**Implementation:**

```python
async def _process_single_email(
    self,
    task_id: UUID,
    email: dict,
    run_id: UUID,
    field_mappings: dict,
    identifier_column: str | None,
    dedup_service,  # DeduplicationService | None
    gmail_adapter,
    gmail_source_type: str,
    sheet_name: str,
    download_link_regex: str,
) -> "EmailProcessingResult":
    """Process a single email during Gmail ingestion with error isolation.

    Extracts files from email, parses rows, and upserts documents with
    per-email transaction handling. Returns detailed result for this email
    including success/failure classification and retry eligibility.

    Args:
        task_id: ID of ingestion task
        email: Email dict from Gmail adapter with message_id, subject, from,
               attachments/download_links, etc.
        run_id: Current ingestion run ID for cancellation check
        field_mappings: Field mapping configuration from task
        identifier_column: Column name for deduplication (if any)
        dedup_service: DeduplicationService instance (or None)
        gmail_adapter: GmailAdapter instance for file downloads
        gmail_source_type: "attachment" or "download_link"
        sheet_name: Sheet name to parse from Excel files
        download_link_regex: Regex pattern for extracting download links

    Returns:
        EmailProcessingResult with outcome classification and error details

    Raises:
        IngestionCanceledError: If run is canceled during processing
    """
    from app.services.email_processing_result import EmailProcessingResult

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
        # Skip if already processed
        if email_message_id and await self._is_email_processed(email_message_id):
            logger.info(
                "Email already processed, skipping",
                message_id=email_message_id,
                subject=email_subject,
            )
            result.is_success = True
            result.is_retryable = False
            return result

        logger.info("Processing Gmail email", subject=email_subject, message_id=email_message_id)

        # Extract files (attachments or download links)
        file_items = []
        try:
            if gmail_source_type == "download_link":
                file_items = await self._download_files_from_links(
                    run_id,
                    email.get("download_links", []),
                    result.errors,  # Pass result.errors to accumulate
                )
                if result.errors:
                    result.rows_failed = len(result.errors)
                    result.error_type = "file_error"
                    result.error_message = "Failed to download files from links"
                    result.is_success = False
                    # File download errors are retryable (might be transient network issues)
                    result.is_retryable = True
                    return result
            else:
                file_items = [
                    {"filename": a["filename"], "data": a["data"]}
                    for a in email.get("attachments", [])
                ]
        except Exception as e:
            logger.error("Failed to extract files from email", error=str(e), message_id=email_message_id)
            result.rows_failed = 1
            result.error_type = "extraction_error"
            result.error_message = f"Failed to extract email files: {str(e)}"
            result.is_success = False
            result.is_retryable = True  # Extraction errors are retryable
            return result

        # If no files found, still mark as success
        if not file_items:
            logger.info("No files found in email", message_id=email_message_id)
            result.is_success = True
            result.is_retryable = False
            return result

        # Process each file in the email
        for file_item in file_items:
            if await self._is_run_stop_requested(run_id):
                raise IngestionCanceledError(
                    result.rows_inserted,
                    result.rows_updated,
                    result.rows_failed
                )

            filename = file_item["filename"]
            content_type = file_item.get("content_type", "")

            # Skip unsupported files
            if not self._is_supported_report_file(filename, content_type):
                logger.warning(
                    "Skipping unsupported file",
                    filename=filename,
                    content_type=content_type,
                    message_id=email_message_id,
                )
                continue

            # Parse rows from file
            try:
                doc_rows, parse_errors = ExcelProcessor.parse_tabular_rows(
                    file_item["data"],
                    filename=filename,
                    sheet_name=sheet_name,
                )

                # Accumulate parse errors
                if parse_errors:
                    result.errors.extend([
                        {"row_number": e.row_number, "error": e.error}
                        for e in parse_errors
                    ])
                    result.rows_failed += len(parse_errors)

            except Exception as e:
                logger.error(
                    "Failed to parse file",
                    filename=filename,
                    error=str(e),
                    message_id=email_message_id,
                )
                result.errors.append({
                    "filename": filename,
                    "error": f"Parse error: {str(e)}"
                })
                result.rows_failed += 1
                result.error_type = "file_error"
                continue

            # Upsert each parsed row
            for row_data in doc_rows:
                if await self._is_run_stop_requested(run_id):
                    raise IngestionCanceledError(
                        result.rows_inserted,
                        result.rows_updated,
                        result.rows_failed
                    )

                try:
                    # Build document payload from row data
                    document_row = self._build_document_payload(row_data, field_mappings)

                    # Upsert with deduplication if enabled
                    if dedup_service:
                        upsert_result = await self._upsert_document_with_dedup_tracking(
                            document_row, identifier_column, dedup_service, run_id
                        )
                    else:
                        upsert_result = await self._upsert_document(document_row, identifier_column)

                    # Track outcome
                    if upsert_result == "inserted":
                        result.rows_inserted += 1
                        result.has_partial_success = True
                    elif upsert_result == "skipped":
                        result.rows_skipped += 1
                    else:  # "updated"
                        result.rows_updated += 1
                        result.has_partial_success = True

                except Exception as e:
                    logger.error(
                        "Error upserting document row",
                        error=str(e),
                        message_id=email_message_id,
                        row_number=row_data.get("row_number", 0),
                    )
                    result.errors.append({
                        "row_number": row_data.get("row_number", 0),
                        "error": f"Upsert error: {str(e)}"
                    })
                    result.rows_failed += 1
                    result.error_type = "row_error"

        # Determine final success state
        if result.rows_failed > 0 and (result.rows_inserted + result.rows_updated) == 0:
            # All rows failed with no successful rows
            result.is_success = False
            result.is_retryable = True
        else:
            # Success if any rows succeeded, or 0 rows with no errors
            result.is_success = result.rows_failed == 0
            result.is_retryable = False

        logger.info(
            "Email processing complete",
            message_id=email_message_id,
            rows_inserted=result.rows_inserted,
            rows_updated=result.rows_updated,
            rows_failed=result.rows_failed,
            is_success=result.is_success,
        )

        return result

    except IngestionCanceledError:
        # Re-raise cancellation to stop all processing
        raise
    except Exception as e:
        # Unexpected error during email processing
        logger.error(
            "Unexpected error processing email",
            message_id=email_message_id,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        result.error_type = "extraction_error"
        result.error_message = f"Unexpected error: {str(e)}"
        result.is_success = False
        result.is_retryable = True
        result.rows_failed += 1
        return result
```

---

## Part 3: Refactored `_ingest_from_gmail_task()` Main Loop

### Replace Email Processing Loop (lines 1188-1297)

**File:** `backend/src/app/services/ingestion_service.py`

**Current Code to Replace** (lines 1188-1297):
```python
# OLD: Email processing loop
for email in emails:
    # ... 110 lines of email/file/row processing logic
```

**New Implementation:**

```python
            # Get FailedEmailService instance if available
            failed_email_service = None
            try:
                from app.services.failed_email_service import FailedEmailService
                failed_email_service = FailedEmailService(self.db)
            except Exception as e:
                logger.warning("FailedEmailService not available", error=str(e))

            # Process each email with per-email savepoint for transaction isolation
            for email in emails:
                if await self._is_run_stop_requested(run_id):
                    raise IngestionCanceledError(rows_inserted, rows_updated, rows_failed)

                email_message_id = email.get("message_id", "")
                email_subject = email.get("subject", "")
                email_sender = email.get("from", "")

                email_transaction_failed = False

                try:
                    # Per-email savepoint: nested transaction for error isolation
                    # If this email fails, it rolls back only this email's changes
                    async with self.db.begin_nested():
                        email_result = await self._process_single_email(
                            task_id=task_id,
                            email=email,
                            run_id=run_id,
                            field_mappings=field_mappings,
                            identifier_column=identifier_column,
                            dedup_service=dedup_service,
                            gmail_adapter=gmail_adapter,
                            gmail_source_type=gmail_source_type,
                            sheet_name=sheet_name,
                            download_link_regex=download_link_regex,
                        )

                        # Accumulate stats from this email
                        rows_inserted += email_result.rows_inserted
                        rows_updated += email_result.rows_updated
                        rows_failed += email_result.rows_failed
                        errors.extend([
                            RowError(
                                row_number=err.get("row_number", 0),
                                error=err.get("error", "Unknown error")
                            )
                            for err in email_result.errors
                        ])

                    # After savepoint commits successfully, record the email as processed
                    if email_message_id:
                        await self._record_processed_email(
                            message_id=email_message_id,
                            subject=email_subject,
                            sender=email_sender,
                            task_id=task_id,
                            rows_inserted=email_result.rows_inserted,
                            rows_updated=email_result.rows_updated,
                            rows_skipped=email_result.rows_skipped,
                            rows_failed=email_result.rows_failed,
                            is_success=email_result.is_success,
                            is_retryable=email_result.is_retryable,
                        )

                    # Queue email for retry if it failed and is retryable
                    if not email_result.is_success and email_result.is_retryable:
                        if failed_email_service:
                            try:
                                await failed_email_service.record_failed_email(
                                    task_id=task_id,
                                    message_id=email_message_id,
                                    subject=email_subject,
                                    sender=email_sender,
                                    failure_reason=email_result.error_type or "row_error",
                                    error_message=email_result.error_message,
                                    is_retryable=True,
                                )
                                logger.info(
                                    "Email queued for retry",
                                    message_id=email_message_id,
                                    failure_reason=email_result.error_type,
                                )
                            except Exception as e:
                                logger.error(
                                    "Failed to queue email for retry",
                                    message_id=email_message_id,
                                    error=str(e),
                                )

                    # Remove UNREAD label if email was processed (success or partial success)
                    if email_result.rows_inserted > 0 or email_result.rows_updated > 0:
                        try:
                            gmail_service = gmail_adapter.service
                            if gmail_service is not None and email_message_id:
                                await gmail_service.users().messages().modify(
                                    userId="me",
                                    id=email_message_id,
                                    body={"removeLabelIds": ["UNREAD"]},
                                ).execute()
                        except Exception as e:
                            logger.warning(
                                "Could not mark email as processed (remove UNREAD)",
                                message_id=email_message_id,
                                error=str(e),
                            )

                except IngestionCanceledError:
                    # Re-raise cancellation to stop all processing
                    raise

                except Exception as e:
                    # Email processing failed completely (savepoint rollback)
                    logger.error(
                        "Failed to process email (transaction rolled back)",
                        message_id=email_message_id,
                        subject=email_subject,
                        error=str(e),
                        traceback=traceback.format_exc(),
                    )
                    rows_failed += 1
                    email_transaction_failed = True

                    # Still record the email as processed but mark as failed
                    if email_message_id:
                        try:
                            await self._record_processed_email(
                                message_id=email_message_id,
                                subject=email_subject,
                                sender=email_sender,
                                task_id=task_id,
                                rows_inserted=0,
                                rows_updated=0,
                                rows_skipped=0,
                                rows_failed=1,
                                is_success=False,
                                is_retryable=True,  # Unexpected errors are retryable
                            )
                        except Exception as record_error:
                            logger.error("Failed to record email processing failure", error=str(record_error))

                    # Queue for retry if retryable
                    if failed_email_service:
                        try:
                            await failed_email_service.record_failed_email(
                                task_id=task_id,
                                message_id=email_message_id,
                                subject=email_subject,
                                sender=email_sender,
                                failure_reason="extraction_error",
                                error_message=str(e),
                                is_retryable=True,
                            )
                            logger.info("Email queued for retry after failure", message_id=email_message_id)
                        except Exception as queue_error:
                            logger.error("Failed to queue email for retry", error=str(queue_error))

                    # Continue to next email instead of failing entire run
                    continue
```

**Key Features:**
1. **Per-email savepoint**: `async with self.db.begin_nested():` creates nested transaction for each email
2. **Error isolation**: Failure in one email rolls back only that email's changes, not entire run
3. **Partial success**: Run continues processing emails even if some fail
4. **Failed email queueing**: Failed emails with `is_retryable=True` are queued for retry
5. **Outcome tracking**: Each email gets `is_success` and `is_retryable` classification
6. **UNREAD label removal**: Only removed if email had some successful rows
7. **Cancellation support**: Respects run cancellation requests

---

## Part 4: Required Imports and Dependencies

### Add to Top of File

**File:** `backend/src/app/services/ingestion_service.py`

**Add/Verify These Imports:**
```python
import traceback  # NEW: For detailed error logging
from app.services.email_processing_result import EmailProcessingResult  # NEW
from app.services.failed_email_service import FailedEmailService  # NEW (lazy import in method)
```

---

## Part 5: Implementation Steps

### Step 1: Update `_record_processed_email()` Signature
- Add `rows_updated`, `is_success`, `is_retryable` parameters
- Update implementation to persist these fields to ProcessedEmail model
- Update docstring with parameter descriptions

### Step 2: Create `_process_single_email()` Method
- Insert before `_ingest_from_gmail_task()` method
- Implement all error handling with proper classification
- Return EmailProcessingResult with classification

### Step 3: Refactor Email Processing Loop
- Replace lines 1188-1297 with new per-email savepoint loop
- Add FailedEmailService initialization
- Add error handling for email transaction failures
- Implement email retry queueing

### Step 4: Testing Strategy

**Unit Tests to Add:**
```python
# Test cases for _process_single_email()
- test_process_email_with_valid_attachments()
- test_process_email_with_parse_errors()
- test_process_email_with_upsert_errors()
- test_process_email_already_processed()
- test_process_email_with_no_files()
- test_process_email_extraction_error()

# Test cases for main loop
- test_gmail_ingest_with_partial_email_failures()
- test_gmail_ingest_per_email_savepoint_isolation()
- test_gmail_ingest_failed_email_queueing()
- test_gmail_ingest_continued_on_single_email_failure()
- test_gmail_ingest_respects_cancellation()
```

**Integration Tests:**
- Test end-to-end with mock Gmail adapter
- Verify failed emails are recorded in FailedEmailQueue
- Verify ProcessedEmail has correct is_success/is_retryable flags
- Verify partial success (some emails succeed, some fail)
- Verify UNREAD label only removed on successful emails

### Step 5: Verification Checklist

- [ ] `_record_processed_email()` accepts new parameters
- [ ] `_process_single_email()` method created and handles all error cases
- [ ] Per-email savepoint used in main loop
- [ ] FailedEmailService integrated for retry queueing
- [ ] Email classification logic correct (is_success, is_retryable)
- [ ] Partial success flows work (some emails succeed, some fail)
- [ ] Cancellation still respected
- [ ] UNREAD label only removed on successful emails
- [ ] All existing tests still pass
- [ ] New unit tests added and passing
- [ ] Integration tests verify per-email isolation

---

## Part 6: Error Classification Reference

### Error Type Classification

| Error Type | Occurrence | Retryable | Notes |
|-----------|-----------|-----------|-------|
| **auth_error** | Gmail auth fails (token invalid) | Maybe | Transient if refresh token valid, permanent if invalid_grant |
| **extraction_error** | Failed to extract email content | Yes | Network issue, corrupted email, etc. - likely transient |
| **file_error** | Failed to download/parse file | Yes | Network issue, file not found, parse error - likely transient |
| **row_error** | Failed to upsert document row | No | Data validation, unique constraint, etc. - not transient |

### Success Classification

| Scenario | is_success | is_retryable | Action |
|----------|-----------|-----------|--------|
| All rows succeeded | True | False | Mark processed, no retry |
| 0 rows, no errors | True | False | Mark processed (normal), no retry |
| Some rows succeeded, some failed | True | False | Mark processed, no retry (partial success) |
| All rows failed, extraction error | False | True | Mark processed, queue for retry |
| Email had file/parse errors | False | True | Mark processed, queue for retry |
| Email couldn't be extracted | False | True | Mark processed, queue for retry |

---

## Part 7: Edge Cases and Special Handling

### Edge Case 1: Already Processed Email
- Check `_is_email_processed()` at start of `_process_single_email()`
- Return success immediately without processing

### Edge Case 2: Email with No Files
- Mark as successful (no error)
- No rows inserted/updated
- Don't queue for retry

### Edge Case 3: Email Already in Failed Queue
- `FailedEmailService.record_failed_email()` upserts existing record
- Increments `error_count` for exponential backoff calculation

### Edge Case 4: Cancellation During Email Processing
- Catch `IngestionCanceledError` and re-raise (don't catch in outer exception handler)
- Savepoint rolls back partial work for current email
- Run stops processing emails

### Edge Case 5: Database Connection Loss During File Processing
- Caught by outer exception handler
- Email marked as failed and queued for retry
- Run continues with next email

### Edge Case 6: Partial File Processing
- If one file succeeds and next file fails:
  - Savepoint rollback affects entire email
  - All changes for email discarded
  - Email queued for retry
  - This prevents partial email states

---

## Part 8: Migration and Backward Compatibility

### Database Changes Required
None! ProcessedEmail model already has `is_success` and `is_retryable` fields added in previous migrations (020).

### Code Changes That Affect Existing Calls
1. Update all calls to `_record_processed_email()` to use new signature
   - Current call: line 1279-1287 (will be replaced by refactored loop)
   - Should not affect other code (only internal method)

2. Verify no other code calls `_ingest_from_gmail_task()` directly
   - Only entry point should be `ingest_task()` method
   - No API changes needed

---

## Part 9: Performance Considerations

### Savepoint Overhead
- **Per-email savepoint**: One savepoint per email (typically < 100ms overhead)
- **Impact**: For 25 emails, ~2.5 second overhead (negligible)
- **Benefit**: Eliminates entire-run rollback for single email failures

### Failed Email Service Calls
- **Async operations**: `record_failed_email()` is async
- **Single database insert**: ~5ms per failed email
- **Impact**: Minimal for typical failure rates (1-2%)

### Memory Usage
- **EmailProcessingResult object**: ~1KB per email
- **Errors list**: Accumulated errors per email (~100 bytes per error)
- **Impact**: Negligible for typical runs

---

## Part 10: Deployment Notes

### Pre-Deployment
1. Run all existing tests to verify no regressions
2. Add new unit tests for `_process_single_email()`
3. Add integration tests for partial success scenarios
4. Verify FailedEmailQueue schema is in place (migration 022)

### Deployment Steps
1. Deploy updated code with new methods
2. Verify celery workers restart cleanly
3. Run manual test of Gmail ingestion with mock failures
4. Monitor logs for any unexpected errors

### Post-Deployment
1. Monitor failed_email_queue table for expected entries
2. Verify retry schedule working (exponential backoff)
3. Monitor ingestion run success rates
4. Verify partial success scenarios are working

---

## Part 11: Future Enhancements

1. **Admin retry UI**: Dashboard to view and manually retry failed emails
2. **Batch retry**: Automatic retry of multiple failed emails on schedule
3. **Failure analytics**: Dashboard showing failure patterns by error type
4. **Exponential backoff tuning**: Configurable retry schedule
5. **Dead letter queue**: Emails that can't be retried (max attempts reached)
