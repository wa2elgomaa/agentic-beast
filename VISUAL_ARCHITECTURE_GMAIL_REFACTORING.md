# Gmail Refactoring - Visual Architecture & Data Flow

## 1. Current Architecture (Before Refactoring)

```
┌─────────────────────────────────────────────────────────────────┐
│ _ingest_from_gmail_task()                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Connect to Gmail (lines 1079-1175)                          │
│     └─ GmailAdapter.connect()                                   │
│     └─ GmailAdapter.get_oauth_config()                          │
│                                                                 │
│  2. Fetch Emails (lines 1177-1185)                              │
│     └─ GmailAdapter.fetch_data()                                │
│                                                                 │
│  3. Process Each Email [MONOLITHIC] (lines 1188-1297)           │
│     ├─ Check if processed                                       │
│     ├─ For each file:                                           │
│     │  ├─ Extract files (attachments or download links)         │
│     │  ├─ Parse rows                                            │
│     │  └─ For each row:                                         │
│     │     ├─ Build document                                     │
│     │     ├─ Upsert with dedup if enabled                       │
│     │     └─ Track inserted/updated/failed                      │
│     ├─ Record ProcessedEmail                                    │
│     └─ Remove UNREAD label                                      │
│                                                                 │
│  4. Cleanup (lines 1299-1313)                                   │
│     └─ GmailAdapter.disconnect()                                │
│                                                                 │
│  PROBLEM: Single email failure → entire run fails               │
│           No error isolation                                    │
│           No retry logic                                        │
└─────────────────────────────────────────────────────────────────┘
           ↓
    ┌──────────────────┐
    │ IngestionTaskRun │ (SUCCESS or FAILED - no partial)
    └──────────────────┘
           ↓
    ┌──────────────────┐
    │ ProcessedEmail   │ (without is_success, is_retryable)
    └──────────────────┘
```

---

## 2. New Architecture (After Refactoring)

```
┌─────────────────────────────────────────────────────────────────┐
│ _ingest_from_gmail_task()                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Connect to Gmail (lines 1079-1175)                          │
│     └─ GmailAdapter.connect()                                   │
│                                                                 │
│  2. Fetch Emails (lines 1177-1185)                              │
│     └─ GmailAdapter.fetch_data()                                │
│                                                                 │
│  3. Initialize Failed Email Service (NEW)                       │
│     └─ FailedEmailService(self.db)                              │
│                                                                 │
│  4. For Each Email with Savepoint (NEW) (lines 1188-1297)       │
│     ├─ Begin Nested Transaction (SAVEPOINT)                     │
│     │  ├─ _process_single_email()                               │
│     │  │  ├─ Check if processed                                 │
│     │  │  ├─ Extract files                                      │
│     │  │  ├─ Parse rows                                         │
│     │  │  ├─ Upsert each row with dedup                         │
│     │  │  ├─ Classify result (success/retryable/partial)        │
│     │  │  └─ Return EmailProcessingResult                       │
│     │  └─ [SAVEPOINT COMMITS OR ROLLS BACK]                     │
│     │                                                            │
│     ├─ Record ProcessedEmail with classification                │
│     │  ├─ is_success: bool                                      │
│     │  └─ is_retryable: bool                                    │
│     │                                                            │
│     ├─ If Failed & Retryable:                                   │
│     │  └─ Queue in FailedEmailQueue with exponential backoff    │
│     │                                                            │
│     └─ Remove UNREAD only if successful                         │
│                                                                 │
│  5. Cleanup (lines 1299-1313)                                   │
│     └─ GmailAdapter.disconnect()                                │
│                                                                 │
│  SUCCESS: Partial success possible                              │
│           Per-email error isolation                             │
│           Automatic retry queueing                              │
└─────────────────────────────────────────────────────────────────┘
           ↓
    ┌──────────────────┐
    │ IngestionTaskRun │ (SUCCESS or FAILED, but may be partial)
    │ (e.g., 5 of 10   │
    │  emails OK)      │
    └──────────────────┘
           ↓
    ┌──────────────────────────┐
    │ ProcessedEmail           │ (with is_success, is_retryable)
    │ Email 1: success=true,   │
    │ Email 2: success=false,  │
    │ Email 3: success=true    │
    └──────────────────────────┘
           ↓
    ┌──────────────────────────┐
    │ FailedEmailQueue         │ (queued for retry with backoff)
    │ Email 2: next_retry in 1h│
    └──────────────────────────┘
```

---

## 3. Per-Email Savepoint Flow

```
START Email Processing
    ↓
┌───────────────────────────────────────┐
│ BEGIN SAVEPOINT (nested transaction)  │
├───────────────────────────────────────┤
│                                       │
│  _process_single_email()              │
│  ├─ Already processed? → return       │
│  ├─ Extract files                     │
│  ├─ Parse rows                        │
│  ├─ For each row:                     │
│  │  ├─ Upsert document  ←────────┐   │
│  │  └─ If error: continue       │   │
│  └─ Return result               │   │
│                                 │   │
│  Result: EmailProcessingResult  │   │
│  ├─ rows_inserted: 5            │   │
│  ├─ rows_updated: 2             │   │
│  ├─ rows_failed: 1              │   │
│  ├─ is_success: true            │   │
│  ├─ is_retryable: false         │   │
│  └─ error_type: null            │   │
│                                 │   │
└───────────────────────────────────────┘
    ↓
    [SAVEPOINT COMMITS - changes persisted]
    ↓
Record ProcessedEmail (with classification)
    ↓
[If Failed & Retryable] Queue in FailedEmailQueue
    ↓
[If Any Success] Remove UNREAD label
    ↓
Continue to Next Email

─────────────────────────────────────────────

VERSUS: Email Processing Fails

START Email Processing
    ↓
┌───────────────────────────────────────┐
│ BEGIN SAVEPOINT (nested transaction)  │
├───────────────────────────────────────┤
│                                       │
│  _process_single_email()              │
│  ├─ Extract files                     │
│  ├─ File not found → Exception        │
│  │                                    │
│  ✗ SAVEPOINT ROLLS BACK               │
│    (all inserted rows discarded)      │
│                                       │
└───────────────────────────────────────┘
    ↓
    [SAVEPOINT ROLLED BACK - no changes]
    ↓
Catch Exception
    ├─ Log error
    ├─ rows_failed += 1
    └─ Continue to Next Email (RUN CONTINUES!)
    ↓
Record ProcessedEmail (failure state)
    ↓
Queue in FailedEmailQueue for retry
    ↓
Continue to Next Email
```

---

## 4. Success Classification Matrix

```
┌────────────────────────────────────────────────────────────────┐
│ EmailProcessingResult Classification Logic                      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ SCENARIO 1: All Rows Succeeded                                │
│ ├─ rows_inserted=5, rows_updated=2, rows_failed=0             │
│ ├─ is_success: TRUE    ✓ (mark as processed, no retry)        │
│ └─ is_retryable: FALSE                                        │
│                                                                │
│ SCENARIO 2: Partial Success (Some Failed)                     │
│ ├─ rows_inserted=5, rows_updated=0, rows_failed=1             │
│ ├─ is_success: TRUE    ✓ (some data made it in)               │
│ └─ is_retryable: FALSE   (don't retry - we got partial data)   │
│                                                                │
│ SCENARIO 3: Email Had Zero Rows (No Data)                     │
│ ├─ rows_inserted=0, rows_updated=0, rows_failed=0             │
│ ├─ is_success: TRUE    ✓ (processed successfully - no rows)    │
│ └─ is_retryable: FALSE                                        │
│                                                                │
│ SCENARIO 4: All Rows Failed + Extraction Error                │
│ ├─ rows_inserted=0, rows_updated=0, rows_failed=3             │
│ ├─ error_type="extraction_error"                              │
│ ├─ is_success: FALSE   ✗ (couldn't extract data)              │
│ └─ is_retryable: TRUE    (likely transient - queue for retry)  │
│                                                                │
│ SCENARIO 5: All Rows Failed + Row Errors                      │
│ ├─ rows_inserted=0, rows_updated=0, rows_failed=5             │
│ ├─ error_type="row_error"                                     │
│ ├─ is_success: FALSE   ✗ (all rows failed)                    │
│ └─ is_retryable: FALSE   (data issue - don't retry)            │
│                                                                │
│ SCENARIO 6: File Parse Error                                  │
│ ├─ rows_inserted=0, rows_updated=0, rows_failed=1             │
│ ├─ error_type="file_error"                                    │
│ ├─ is_success: FALSE   ✗ (couldn't parse)                     │
│ └─ is_retryable: TRUE    (likely transient - queue for retry)  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 5. Error Type Classification

```
┌─────────────────────────────────────────────────────────────┐
│ Email Processing Error Paths                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Error During:           │ Error Type       │ Retryable    │
│ ─────────────────────────────────────────────────────────  │
│ Gmail auth              │ auth_error       │ MAYBE        │
│ Email extraction        │ extraction_error │ YES (likely) │
│ File download           │ file_error       │ YES (likely) │
│ File parse (Excel)      │ file_error       │ YES (likely) │
│ Row validation          │ row_error        │ NO (data)    │
│ Database upsert         │ row_error        │ NO (data)    │
│                                                             │
│ Logic:                                                       │
│ ├─ Extraction/File errors → likely transient → RETRY       │
│ ├─ Row errors → likely data issue → NO RETRY               │
│ └─ Auth errors → depends on cause → MAYBE                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Database State After Processing

```
BEFORE: Single Email Email Failure → Entire Run Failed

┌─────────────────────────────────┐
│ IngestionTaskRun                │
│ id: run_123                     │
│ status: FAILED                  │
│ rows_inserted: 0 (ROLLBACK)     │
│ error: "Email 2 failed"         │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│ ProcessedEmail                  │
│ Email 1: ✓ (processed)          │
│ Email 2: ✗ (never processed)    │
│ Email 3: ✗ (never processed)    │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│ FailedEmailQueue                │
│ (empty - no retry tracking)     │
└─────────────────────────────────┘

AFTER: Same Scenario → Partial Success Tracked

┌─────────────────────────────────┐
│ IngestionTaskRun                │
│ id: run_123                     │
│ status: SUCCESS (partial)       │
│ rows_inserted: 5 (Email 1+3)    │
│ error_count: 1 (Email 2)        │
└─────────────────────────────────┘
           ↓
┌────────────────────────────────────────┐
│ ProcessedEmail                         │
│ Email 1: ✓ (is_success=true)           │
│ Email 2: ✗ (is_success=false,          │
│          is_retryable=true)            │
│ Email 3: ✓ (is_success=true)           │
└────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│ FailedEmailQueue                     │
│ Email 2: queued, retry in 1 hour     │
│ failure_reason: "extraction_error"   │
│ error_count: 1                       │
└──────────────────────────────────────┘
```

---

## 7. Exponential Backoff Schedule

```
Email Fails During Processing:
    ↓
1st Failure:
├─ Add to FailedEmailQueue
├─ error_count: 1
├─ next_retry_at: NOW + 1 HOUR
└─ Scheduled for automatic retry
    ↓
[1 hour later] Automatic Retry Attempted:
    ├─ Email processing fails again
    └─ Update existing record
    ↓
2nd Failure:
├─ Keep in FailedEmailQueue
├─ error_count: 2
├─ next_retry_at: NOW + 4 HOURS
└─ Scheduled for automatic retry
    ↓
[4 hours later] Automatic Retry Attempted:
    ├─ Email processing fails again
    └─ Update existing record
    ↓
3rd+ Failure:
├─ Keep in FailedEmailQueue
├─ error_count: 3+
├─ next_retry_at: NOW + 365 DAYS
├─ Requires manual intervention
└─ Admin can still click "Retry" to override
```

---

## 8. Integration Points

```
┌──────────────────────────────────────────────────────────────┐
│ _ingest_from_gmail_task() Integration                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ GmailAdapter (existing)                                 │
│  │  ├─ .connect()                                           │
│  │  ├─ .fetch_data()                                        │
│  │  ├─ .service.users().messages().modify()                 │
│  │  └─ .disconnect()                                        │
│  │                                                          │
│  ├─ EmailProcessingResult (NEW in _process_single_email)    │
│  │  ├─ message_id, subject, sender                          │
│  │  ├─ rows_inserted, rows_updated, rows_failed             │
│  │  ├─ is_success, is_retryable                             │
│  │  └─ error_type, error_message                            │
│  │                                                          │
│  ├─ FailedEmailService (NEW in main loop)                   │
│  │  ├─ .record_failed_email()                               │
│  │  └─ .increment_retry_count()                             │
│  │                                                          │
│  ├─ ProcessedEmail (existing, updated)                      │
│  │  ├─ message_id (unique)                                  │
│  │  ├─ is_success (NEW)                                     │
│  │  └─ is_retryable (NEW)                                   │
│  │                                                          │
│  ├─ Database (AsyncSession)                                 │
│  │  ├─ .begin_nested() → savepoint (NEW)                    │
│  │  └─ .execute() → queries (existing)                      │
│  │                                                          │
│  ├─ DeduplicationService (existing)                         │
│  │  └─ ._upsert_document_with_dedup_tracking()              │
│  │                                                          │
│  └─ ExcelProcessor (existing)                               │
│     └─ .parse_tabular_rows()                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. Method Call Stack

```
ingest_task(task_id) [external entry point]
    ↓
_ingest_from_gmail_task(task, run_id)
    ├─ GmailAdapter.connect()
    ├─ GmailAdapter.fetch_data()
    ├─ FailedEmailService.__init__()
    │
    └─ for email in emails:
        ├─ begin_nested() [SAVEPOINT]
        │   ↓
        │   └─ _process_single_email(email, ...) [NEW METHOD]
        │       ├─ _is_email_processed()
        │       ├─ _download_files_from_links()
        │       ├─ ExcelProcessor.parse_tabular_rows()
        │       ├─ _build_document_payload()
        │       ├─ _upsert_document_with_dedup_tracking()
        │       ├─ [accumulate errors & stats]
        │       └─ return EmailProcessingResult
        │   ↓
        │   [SAVEPOINT COMMITS or ROLLS BACK]
        │
        ├─ _record_processed_email() [UPDATED SIGNATURE]
        ├─ FailedEmailService.record_failed_email()
        └─ GmailAdapter.service.users().messages().modify()

    └─ GmailAdapter.disconnect()
```

---

## 10. Code Organization Comparison

### BEFORE: Monolithic Loop
```
_ingest_from_gmail_task() [1055-1313]
├─ OAuth setup [1055-1175]
├─ Email fetch [1177-1185]
├─ MONOLITHIC EMAIL PROCESSING [1188-1297] ← 110 lines inline
│  ├─ Already processed check
│  ├─ File extraction
│  ├─ File parsing
│  ├─ Row upsert (3 nested loops)
│  ├─ Error handling (mixed with logic)
│  ├─ Email recording
│  └─ Label removal
└─ Cleanup [1299-1313]
```

### AFTER: Extracted Method
```
_process_single_email() [NEW - ~230 lines] ← Email logic extracted
├─ Already processed check
├─ File extraction
├─ File parsing
├─ Row upsert (3 nested loops)
├─ Error classification
└─ Return result

_ingest_from_gmail_task() [1055-1313]
├─ OAuth setup [1055-1175]
├─ Email fetch [1177-1185]
├─ EMAIL PROCESSING WITH SAVEPOINT [1188-1297] ← Refactored to 120 lines
│  ├─ begin_nested() savepoint
│  ├─ Call _process_single_email()
│  ├─ Record processed email
│  ├─ Queue for retry if needed
│  └─ Error handling per-email
└─ Cleanup [1299-1313]
```

---

## 11. Testing Strategy Diagram

```
┌───────────────────────────────────────────┐
│ Test Coverage                             │
├───────────────────────────────────────────┤
│                                           │
│ Unit Tests:                               │
│ ├─ test_process_single_email_*            │
│ │  ├─ Already processed                  │
│ │  ├─ Parse errors                       │
│ │  ├─ Upsert errors                      │
│ │  ├─ No files                           │
│ │  └─ Success classification             │
│ │                                         │
│ ├─ test_record_processed_email_*          │
│ │  └─ New fields (is_success, is_retryable)
│ │                                         │
│ └─ test_failed_email_service_*            │
│    └─ Retry queueing                     │
│                                           │
│ Integration Tests:                        │
│ ├─ test_gmail_ingest_partial_failure      │
│ │  └─ Some emails succeed, some fail     │
│ ├─ test_gmail_ingest_savepoint_isolation  │
│ │  └─ Email failure doesn't affect others│
│ ├─ test_gmail_ingest_retry_queueing       │
│ │  └─ Failed emails in FailedEmailQueue  │
│ └─ test_gmail_ingest_cancellation         │
│    └─ Run cancellation still respected    │
│                                           │
│ End-to-End Tests:                         │
│ ├─ test_gmail_sync_complete_flow          │
│ │  └─ 10 emails, 2 fail, 8 succeed       │
│ └─ test_gmail_retry_mechanism             │
│    └─ Failed email retried after 1 hour  │
│                                           │
└───────────────────────────────────────────┘
```

---

## 12. Deployment Timeline

```
Timeline → │
           │
Week 1:    ├─ Code Review (2 days)
           │  ├─ Architecture review
           │  ├─ Error handling review
           │  └─ Test coverage review
           │
           ├─ Unit Tests (2 days)
           │  ├─ _process_single_email() tests
           │  ├─ Error classification tests
           │  └─ Integration tests
           │
Week 2:    ├─ Staging Deployment (1 day)
           │  ├─ Deploy to staging
           │  ├─ Run E2E tests
           │  ├─ Load testing if needed
           │  └─ Team acceptance testing
           │
           ├─ Production Deployment (1 day)
           │  ├─ Deploy to production
           │  ├─ Monitor for 1 hour
           │  └─ Verify partial success working
           │
           └─ Post-Deployment (2 days)
              ├─ Monitor error rates
              ├─ Verify retry mechanism
              ├─ Check ProcessedEmail records
              └─ Document lessons learned
```

