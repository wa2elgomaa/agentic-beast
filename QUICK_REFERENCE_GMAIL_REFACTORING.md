# Gmail Refactoring - Quick Reference & Code Snippets

## Overview

This document provides side-by-side comparison and quick implementation reference for the Gmail ingestion refactoring.

---

## 1. Updated Signature - _record_processed_email()

### BEFORE:
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

### AFTER:
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
    rows_updated: int = 0,           # NEW
    is_success: bool = True,         # NEW
    is_retryable: bool = False,      # NEW
) -> None:
```

### Update Implementation (lines 324-351):
```python
stmt = (
    pg_insert(ProcessedEmail)
    .values(
        message_id=message_id,
        task_id=task_id,
        subject=subject,
        sender=sender,
        rows_inserted=rows_inserted,
        rows_updated=rows_updated,      # NEW
        rows_skipped=rows_skipped,
        rows_failed=rows_failed,
        is_success=is_success,          # NEW
        is_retryable=is_retryable,      # NEW
        processed_at=func.now(),
    )
    .on_conflict_do_nothing(index_elements=["message_id"])
)
await self.db.execute(stmt)
```

---

## 2. New Method - _process_single_email()

### Location: Insert before _ingest_from_gmail_task() (before line 1055)

### Skeleton (40 lines):
```python
async def _process_single_email(
    self,
    task_id: UUID,
    email: dict,
    run_id: UUID,
    field_mappings: dict,
    identifier_column: str | None,
    dedup_service,
    gmail_adapter,
    gmail_source_type: str,
    sheet_name: str,
    download_link_regex: str,
) -> "EmailProcessingResult":
    """Process a single email with error isolation.

    Returns EmailProcessingResult with outcome classification.
    """
    from app.services.email_processing_result import EmailProcessingResult

    result = EmailProcessingResult(
        message_id=email.get("message_id", ""),
        subject=email.get("subject", ""),
        sender=email.get("from", ""),
    )

    try:
        # 1. Check if already processed
        # 2. Extract files (attachments or download links)
        # 3. Parse rows from each file
        # 4. Upsert each row with dedup if enabled
        # 5. Classify success/retry status
        # 6. Return result
        pass
    except IngestionCanceledError:
        raise
    except Exception as e:
        result.is_success = False
        result.is_retryable = True
        return result

    return result
```

### Key Logic Sections:

**1. Already Processed Check:**
```python
if email_message_id and await self._is_email_processed(email_message_id):
    logger.info("Email already processed, skipping", message_id=email_message_id)
    result.is_success = True
    result.is_retryable = False
    return result
```

**2. File Extraction:**
```python
if gmail_source_type == "download_link":
    file_items = await self._download_files_from_links(
        run_id, email.get("download_links", []), result.errors
    )
else:
    file_items = [
        {"filename": a["filename"], "data": a["data"]}
        for a in email.get("attachments", [])
    ]

if not file_items:
    result.is_success = True
    result.is_retryable = False
    return result
```

**3. Row Upsert Loop:**
```python
for row_data in doc_rows:
    try:
        document_row = self._build_document_payload(row_data, field_mappings)
        if dedup_service:
            upsert_result = await self._upsert_document_with_dedup_tracking(
                document_row, identifier_column, dedup_service, run_id
            )
        else:
            upsert_result = await self._upsert_document(document_row, identifier_column)

        if upsert_result == "inserted":
            result.rows_inserted += 1
            result.has_partial_success = True
        elif upsert_result == "skipped":
            result.rows_skipped += 1
        else:
            result.rows_updated += 1
            result.has_partial_success = True
    except Exception as e:
        result.errors.append({"row_number": row_data.get("row_number", 0), "error": str(e)})
        result.rows_failed += 1
        result.error_type = "row_error"
```

**4. Success Classification:**
```python
if result.rows_failed > 0 and (result.rows_inserted + result.rows_updated) == 0:
    result.is_success = False
    result.is_retryable = True
else:
    result.is_success = result.rows_failed == 0
    result.is_retryable = False
```

---

## 3. Refactored Main Loop - _ingest_from_gmail_task()

### Current Code (lines 1188-1297):
- Nested for loops: email → file → row
- No error isolation
- No retry queueing
- ~110 lines of complex logic

### New Code (lines 1188-1297 REPLACED):

#### Part A: Initialize Failed Email Service
```python
# Get FailedEmailService instance if available
failed_email_service = None
try:
    from app.services.failed_email_service import FailedEmailService
    failed_email_service = FailedEmailService(self.db)
except Exception as e:
    logger.warning("FailedEmailService not available", error=str(e))
```

#### Part B: Per-Email Savepoint Loop
```python
for email in emails:
    if await self._is_run_stop_requested(run_id):
        raise IngestionCanceledError(rows_inserted, rows_updated, rows_failed)

    email_message_id = email.get("message_id", "")
    email_subject = email.get("subject", "")
    email_sender = email.get("from", "")

    try:
        # Per-email savepoint: nested transaction
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

            # Accumulate stats
            rows_inserted += email_result.rows_inserted
            rows_updated += email_result.rows_updated
            rows_failed += email_result.rows_failed
            errors.extend([
                RowError(row_number=e.get("row_number", 0), error=e.get("error"))
                for e in email_result.errors
            ])

        # Record email as processed
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

        # Queue for retry if failed and retryable
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
                    logger.info("Email queued for retry", message_id=email_message_id)
                except Exception as e:
                    logger.error("Failed to queue email for retry", error=str(e))

        # Remove UNREAD label if successful
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
                logger.warning("Could not mark email as processed", error=str(e))

    except IngestionCanceledError:
        raise
    except Exception as e:
        # Email processing failed completely
        logger.error("Failed to process email", message_id=email_message_id, error=str(e))
        rows_failed += 1

        # Record failure
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
                    is_retryable=True,
                )
            except Exception:
                pass

        # Queue for retry
        if failed_email_service and email_message_id:
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
            except Exception:
                pass

        # Continue to next email
        continue
```

---

## 4. Implementation Checklist

### Phase 1: Update Existing Method
- [ ] Add `rows_updated`, `is_success`, `is_retryable` to `_record_processed_email()` signature
- [ ] Update docstring with new parameters
- [ ] Update upsert statement to include new fields
- [ ] Test calls with new parameters work

### Phase 2: Create New Method
- [ ] Create `_process_single_email()` method
- [ ] Add docstring with parameters and return type
- [ ] Implement already-processed check
- [ ] Implement file extraction logic
- [ ] Implement file parsing and row upsert loop
- [ ] Implement error classification logic
- [ ] Add error type and message tracking
- [ ] Test with mock data

### Phase 3: Refactor Main Loop
- [ ] Replace lines 1188-1297 with new savepoint loop
- [ ] Initialize FailedEmailService
- [ ] Add per-email savepoint with `async with self.db.begin_nested():`
- [ ] Call `_process_single_email()` with all parameters
- [ ] Record processed email with new fields
- [ ] Queue failed emails for retry
- [ ] Handle outer exception for unexpected errors
- [ ] Ensure cancellation still works

### Phase 4: Testing
- [ ] Run existing tests - all passing
- [ ] Test `_process_single_email()` with valid attachments
- [ ] Test `_process_single_email()` with parse errors
- [ ] Test `_process_single_email()` with upsert errors
- [ ] Test `_process_single_email()` with no files
- [ ] Test main loop with partial failures
- [ ] Test main loop with cancellation
- [ ] Test retry queueing works
- [ ] Test ProcessedEmail records have correct flags

### Phase 5: Deployment
- [ ] Review code with team
- [ ] Verify all linting/formatting passes
- [ ] Create PR with description of changes
- [ ] Verify CI passes
- [ ] Deploy to staging
- [ ] Manual testing with Gmail task
- [ ] Monitor logs for 30 minutes
- [ ] Deploy to production

---

## 5. Key Differences Summary

| Aspect | OLD | NEW |
|--------|-----|-----|
| Error Scope | Entire run | Single email |
| Rollback | Full run rollback | Per-email savepoint rollback |
| Failure Handling | Stop immediately | Continue to next email |
| Partial Success | Fails entire run | Valid outcome |
| Failed Email Tracking | Not tracked | Recorded in FailedEmailQueue |
| Retry Logic | Manual | Automatic with exponential backoff |
| UNREAD Label | Always removed | Only if successful |
| Code Organization | 110-line monolithic loop | Extracted `_process_single_email()` method |

---

## 6. Error Handling Flow

```
Email Processing Start
    ↓
    [Savepoint Created]
    ↓
1. Already Processed?
   ├─ Yes → Return Success (is_retryable=False)
   └─ No → Continue
    ↓
2. Extract Files
   ├─ Error → Return with error_type="extraction_error" (is_retryable=True)
   ├─ No files → Return Success (is_retryable=False)
   └─ Success → Continue
    ↓
3. Parse Files & Upsert Rows
   ├─ Parse Error → Accumulate error, continue to next file
   ├─ Upsert Success → Track inserted/updated
   ├─ Upsert Error → Accumulate error, continue to next row
   └─ Repeat for all files/rows
    ↓
4. Classify Outcome
   ├─ All succeeded? → is_success=True, is_retryable=False
   ├─ Some succeeded? → is_success=True, is_retryable=False (partial success)
   ├─ All failed + extraction error? → is_success=False, is_retryable=True
   └─ All failed + row errors? → is_success=False, is_retryable=False
    ↓
5. Post-Processing
   ├─ Record ProcessedEmail with classification
   ├─ Queue for retry if is_retryable=True
   ├─ Remove UNREAD if any rows succeeded
   └─ Return result
    ↓
[Savepoint Committed OR Rolled Back]
    ↓
Continue to Next Email
```

---

## 7. Parameter Passing Reference

### _process_single_email() Parameters:
```python
task_id: UUID                       # Task being ingested
email: dict                         # Email from Gmail adapter
run_id: UUID                        # Ingestion run ID
field_mappings: dict                # Field → Column mapping
identifier_column: str | None       # Column for dedup
dedup_service: DeduplicationService | None
gmail_adapter: GmailAdapter         # For downloading files
gmail_source_type: str              # "attachment" or "download_link"
sheet_name: str                     # Excel sheet to parse
download_link_regex: str            # Regex for finding links
```

### EmailProcessingResult Return:
```python
{
    "message_id": str,
    "subject": str | None,
    "sender": str | None,
    "rows_inserted": int,
    "rows_updated": int,
    "rows_skipped": int,
    "rows_failed": int,
    "is_success": bool,             # All rows succeeded or 0 rows/no errors
    "has_partial_success": bool,    # Some rows succeeded despite failures
    "error_type": str | None,       # auth_error|extraction_error|row_error|file_error
    "error_message": str | None,
    "errors": list[dict],           # Detailed per-error list
    "is_retryable": bool            # Computed from is_success & error_type
}
```

---

## 8. Database Schema (Already in Place)

### ProcessedEmail Table (from migration 020):
```sql
processed_emails:
  id (pk)
  message_id (unique)
  task_id (fk)
  subject
  sender
  rows_inserted
  rows_updated          ← NEW
  rows_skipped
  rows_failed
  is_success            ← NEW
  is_retryable          ← NEW
  processed_at
```

### FailedEmailQueue Table (from migration 022):
```sql
failed_email_queue:
  id (pk)
  task_id (fk)
  message_id
  subject
  sender
  failure_reason (auth_error|extraction_error|row_error|file_error)
  error_message
  error_count
  last_attempted_at
  next_retry_at (exponential backoff)
  created_at
  updated_at
```

---

## 9. Quick Testing Commands

```bash
# Run existing ingestion tests
cd /Users/wgomaa/Work/TNN/AI\ Project/The\ Beast/agentic-beast
pytest tests/ingestion_service_test.py -v

# Run with coverage
pytest tests/ingestion_service_test.py --cov=app.services.ingestion_service

# Run only Gmail-related tests
pytest tests/ -k "gmail" -v

# Check for linting issues
ruff check backend/src/app/services/ingestion_service.py

# Format code
ruff format backend/src/app/services/ingestion_service.py
```

---

## 10. Troubleshooting Guide

### Issue: Savepoint commits but email result shows failure
**Cause**: Result classification logic may be wrong
**Check**: Verify `is_success` and `is_retryable` logic in step 4 of `_process_single_email()`

### Issue: Email marked processed but also queued for retry
**Cause**: Recording happens before retry queueing check
**Check**: `is_retryable` field should prevent actual retry (scheduled for future)

### Issue: UNREAD label not removed from failed emails
**Expected**: This is correct! Only remove for successful emails
**Verify**: Check `if email_result.rows_inserted > 0 or email_result.rows_updated > 0:`

### Issue: FailedEmailService not available error
**Cause**: Import may fail at runtime
**Solution**: Handled gracefully - logs warning, continues without queueing

### Issue: Savepoint rollback not working
**Cause**: Likely SQLAlchemy version mismatch
**Check**: Verify `async with self.db.begin_nested():` syntax for your version

