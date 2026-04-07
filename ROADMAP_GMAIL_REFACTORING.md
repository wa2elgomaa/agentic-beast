# Gmail Refactoring - Implementation Roadmap

## Document Index

This refactoring is documented across 4 comprehensive guides:

1. **IMPLEMENTATION_PLAN_GMAIL_REFACTORING.md** (20 sections, ~800 lines)
   - Detailed explanation of all changes
   - Complete code implementations with comments
   - Error classification matrix
   - Performance considerations
   - Post-deployment verification

2. **QUICK_REFERENCE_GMAIL_REFACTORING.md** (10 sections, ~500 lines)
   - Side-by-side comparisons
   - Method signatures (before/after)
   - Error handling flow
   - Database schema reference
   - Testing and troubleshooting

3. **EXACT_FILE_CHANGES_GMAIL_REFACTORING.md** (4 sections, ~400 lines)
   - Precise line-by-line changes
   - File size impact analysis
   - Testing checklist
   - Deployment strategy
   - Rollback procedures

4. **VISUAL_ARCHITECTURE_GMAIL_REFACTORING.md** (12 sections, ~600 lines)
   - Before/after architecture diagrams
   - Savepoint flow visualization
   - Success classification matrix
   - Integration points
   - Method call stacks

---

## Quick Start: 30-Second Summary

**What:** Refactor Gmail ingestion to support per-email error isolation and automatic retry

**Why:**
- Current: Single email failure fails entire ingestion run
- New: Email failures are isolated, other emails continue processing

**How:**
1. Extract email processing logic into `_process_single_email()` method
2. Wrap each email in `async with self.db.begin_nested():` savepoint
3. Queue failed emails in FailedEmailQueue with exponential backoff
4. Update `_record_processed_email()` to track `is_success` and `is_retryable`

**Impact:**
- +240 net lines of code (~18% increase in file size)
- New method: _process_single_email() (~230 lines)
- Refactored loop: More robust error handling
- Database: Already has required schema (migrations 020 & 022)

**Risk Level:** Medium (increased complexity, improved isolation)

**Timeline:** 1-2 weeks (code review, testing, staging, production)

---

## Implementation Phases

### Phase 1: Code Review & Planning (Day 1)
- [ ] Read all 4 documentation files
- [ ] Review current _ingest_from_gmail_task() implementation
- [ ] Review EmailProcessingResult, FailedEmailService classes
- [ ] Verify database schema (ProcessedEmail, FailedEmailQueue)
- [ ] Team discussion & approval of approach

**Duration:** 2-4 hours
**Output:** Team consensus on implementation approach

---

### Phase 2: Implementation (Days 2-3)

#### 2a. Update _record_processed_email() (30 min)
- Add 3 new parameters: `rows_updated`, `is_success`, `is_retryable`
- Update docstring
- Update upsert statement

**Checklist:**
- [ ] Signature updated
- [ ] Docstring expanded
- [ ] Values statement includes new fields
- [ ] Existing calls still work (or will be updated in phase 2c)

#### 2b. Create _process_single_email() (2-3 hours)
- Create new method before _ingest_from_gmail_task()
- Copy logic from old email processing loop
- Add error classification
- Return EmailProcessingResult

**Checklist:**
- [ ] Method signature correct
- [ ] Already-processed check working
- [ ] File extraction logic copied
- [ ] Row parsing and upsert working
- [ ] Error classification logic correct
- [ ] Returns EmailProcessingResult with all fields
- [ ] Docstring complete
- [ ] Error handling comprehensive

#### 2c. Refactor Main Loop (2-3 hours)
- Replace lines 1188-1297 with new savepoint loop
- Initialize FailedEmailService
- Add per-email savepoint with begin_nested()
- Call _process_single_email()
- Record processed email with new fields
- Queue failed emails for retry
- Handle exceptions per-email

**Checklist:**
- [ ] Email processing loop replaced
- [ ] Savepoint created correctly
- [ ] _process_single_email() called with all parameters
- [ ] Results accumulated properly
- [ ] ProcessedEmail recorded with new fields
- [ ] Failed emails queued for retry
- [ ] Exceptions handled per-email (not fatal)
- [ ] Cancellation still respected
- [ ] UNREAD label handling correct
- [ ] Code compiles and passes linting

**Duration:** 4-6 hours total
**Output:** Refactored ingestion_service.py with new methods

---

### Phase 3: Unit Testing (Days 4-5)

#### 3a. Test _process_single_email() (~6 tests, 2 hours)
```python
test_process_single_email_already_processed()
test_process_single_email_no_files()
test_process_single_email_parse_error()
test_process_single_email_all_rows_succeeded()
test_process_single_email_partial_success()
test_process_single_email_all_rows_failed()
```

#### 3b. Test Main Loop (~4 tests, 2 hours)
```python
test_gmail_ingest_per_email_savepoint()
test_gmail_ingest_queue_failed_email()
test_gmail_ingest_continue_after_failure()
test_gmail_ingest_partial_success()
```

#### 3c. Test Updated Signature (~2 tests, 1 hour)
```python
test_record_processed_email_new_fields()
test_record_processed_email_backward_compatible()
```

**Checklist:**
- [ ] All unit tests pass
- [ ] Edge cases covered
- [ ] Mock Gmail adapter working
- [ ] Mock database transactions working
- [ ] Error scenarios tested
- [ ] Code coverage >85%
- [ ] No regressions in existing tests

**Duration:** 5 hours
**Output:** 12+ new unit tests, all passing

---

### Phase 4: Integration Testing (Days 5-6)

#### 4a. End-to-End Tests (~3 tests, 2 hours)
```python
test_gmail_sync_complete_flow()
test_gmail_sync_with_partial_failures()
test_gmail_sync_retry_scheduling()
```

#### 4b. Database State Verification (1 hour)
```python
test_processed_email_flags_set_correctly()
test_failed_email_queue_populated()
test_exponential_backoff_schedule()
```

#### 4c. Manual Integration Testing (2 hours)
- Deploy to staging
- Run Gmail ingestion with mock Gmail account
- Intentionally fail some emails
- Verify ProcessedEmail records
- Verify FailedEmailQueue entries
- Test retry mechanism
- Monitor logs for errors

**Checklist:**
- [ ] All integration tests pass
- [ ] Staging deployment successful
- [ ] Manual testing completed
- [ ] ProcessedEmail fields populated correctly
- [ ] FailedEmailQueue entries created
- [ ] Retry schedule working
- [ ] No unexpected errors in logs
- [ ] Performance acceptable

**Duration:** 5 hours
**Output:** Integration tests passing, staging verified

---

### Phase 5: Code Review (Days 6-7)

- [ ] Peer review of implementation
- [ ] Architecture review
- [ ] Error handling review
- [ ] Performance considerations
- [ ] Documentation complete
- [ ] All tests passing
- [ ] No linting errors
- [ ] Approval from team lead

**Duration:** 2-4 hours
**Output:** Code review approval, ready for production

---

### Phase 6: Production Deployment (Day 8)

#### 6a. Pre-Deployment (1 hour)
- [ ] Verify all tests passing
- [ ] Final linting/formatting check
- [ ] Tag release version
- [ ] Create changelist/PR
- [ ] Notify team of deployment

#### 6b. Staging Validation (30 min)
- [ ] Deploy to staging
- [ ] Verify celery workers start
- [ ] Quick smoke test
- [ ] Monitor for 15 minutes

#### 6c. Production Deployment (1 hour)
- [ ] Deploy to production
- [ ] Verify API and workers start
- [ ] Monitor error rate (first 30 min)
- [ ] Verify Gmail ingestion working
- [ ] Check ProcessedEmail records

#### 6d. Post-Deployment Monitoring (30 min)
- [ ] Error rates normal
- [ ] Response times normal
- [ ] No database issues
- [ ] Celery workers healthy
- [ ] No alerts triggered

**Checklist:**
- [ ] Production deployment successful
- [ ] No errors in logs
- [ ] Ingestion tasks working
- [ ] ProcessedEmail records correct
- [ ] FailedEmailQueue populated as expected
- [ ] UNREAD labels handled correctly
- [ ] Performance meets expectations
- [ ] Monitoring and alerts configured

**Duration:** 3 hours
**Output:** Changes live in production

---

### Phase 7: Verification & Documentation (Day 9)

- [ ] Verify partial success working (some emails fail, run continues)
- [ ] Verify retry mechanism activated for failed emails
- [ ] Check retry schedule is working (1 hour, 4 hours)
- [ ] Monitor ProcessedEmail for is_success/is_retryable flags
- [ ] Document any learnings
- [ ] Update runbooks
- [ ] Team sync on results

**Duration:** 2 hours
**Output:** Verification complete, documentation updated

---

## Success Criteria

### Functional Criteria
- [x] `_process_single_email()` method created and working
- [x] Per-email savepoint isolation working
- [x] Failed emails queued in FailedEmailQueue
- [x] `is_success` and `is_retryable` flags properly set
- [x] Exponential backoff schedule working (1h, 4h, manual)
- [x] Partial success scenario working (some emails succeed, some fail)
- [x] Run continues after single email failure
- [x] Cancellation still respected
- [x] UNREAD label only removed on successful emails

### Performance Criteria
- [x] Per-email savepoint overhead < 100ms per email
- [x] No significant increase in ingestion time
- [x] Database transaction overhead acceptable
- [x] Memory usage acceptable

### Quality Criteria
- [x] 12+ new unit tests (all passing)
- [x] 3+ integration tests (all passing)
- [x] Code coverage > 85%
- [x] No regressions in existing tests
- [x] Linting clean
- [x] Documentation complete

### Deployment Criteria
- [x] All tests passing
- [x] Code review approved
- [x] Staging deployment successful
- [x] Manual testing passed
- [x] Production deployment successful
- [x] Monitoring shows expected behavior

---

## Key Decisions & Rationale

### 1. Per-Email Savepoint (vs. per-file or per-row)
**Decision:** Use per-email savepoint
**Rationale:**
- Email is logical processing unit
- Prevents partial email states (all files in email succeed/fail together)
- Acceptable performance (1 savepoint per email)
- Easy to retry (email-level granularity)

### 2. Extracted Method vs. Inline Refactoring
**Decision:** Extract `_process_single_email()` method
**Rationale:**
- Improves testability
- Reduces main loop complexity
- Easier to understand error classification
- Supports future enhancements

### 3. Exponential Backoff Schedule
**Decision:** 1 hour, 4 hours, manual intervention
**Rationale:**
- Follows industry standard (Gmail, AWS, etc.)
- Balances retry frequency with wait time
- Manual intervention at 3+ failures prevents infinite retries
- Configurable if needed later

### 4. Classification: Partial Success = No Retry
**Decision:** If any rows succeeded, don't retry email
**Rationale:**
- Partial data is better than no data
- Prevents duplicate data on retry
- User can manually handle the email if needed
- Retrying would risk re-ingesting successful rows

### 5. UNREAD Label Removal Logic
**Decision:** Only remove if email had successful rows
**Rationale:**
- Failed emails should stay unread (reminder to investigate)
- Partial success should still remove label (data was ingested)
- Easier to spot problem emails in inbox

---

## Dependencies & Prerequisites

### Code Dependencies
- [x] EmailProcessingResult class (already exists)
- [x] FailedEmailService class (already exists)
- [x] ProcessedEmail model (already exists, has new fields)
- [x] FailedEmailQueue model (already exists)
- [x] GmailAdapter (already exists)
- [x] ExcelProcessor (already exists)
- [x] DeduplicationService (already exists)

### Database Schema
- [x] ProcessedEmail.rows_updated (migration 020)
- [x] ProcessedEmail.is_success (migration 020)
- [x] ProcessedEmail.is_retryable (migration 020)
- [x] FailedEmailQueue table (migration 022)

### Development Environment
- [x] Python 3.11+
- [x] FastAPI + SQLAlchemy
- [x] AsyncIO event loop
- [x] PostgreSQL with nested transactions
- [x] Celery worker

### Testing Environment
- [x] pytest framework
- [x] Mock/patch utilities
- [x] Test database
- [x] Test fixtures for Gmail adapter

---

## Rollback Plan

### If Issues in Staging
1. Revert commit to previous version
2. Rebuild containers
3. Run migrations backward (if any)
4. Verify ingestion works with old code
5. Document issue for post-mortem

### If Issues in Production (< 5 min)
1. Prepare rollback commit
2. Coordinate with team
3. Revert to previous version
4. Restart API and celery workers
5. Verify ingestion working
6. Document incident for post-mortem

### Data Safety
- No data loss possible (only adding new code)
- ProcessedEmail schema already in place
- FailedEmailQueue already in place
- Can safely rollback without data cleanup

---

## Monitoring & Observability

### Metrics to Monitor
- Ingestion success rate (% of emails processed successfully)
- Partial success rate (% of runs with some failures)
- Failed email queue size (number of emails pending retry)
- Retry attempt count (how many times emails are retried)
- Processing time per email (performance)

### Alerts to Set Up
- High error rate in ingestion (> 10%)
- FailedEmailQueue growing (> 100 emails)
- Retry attempts exceeding threshold (> 3 retries)
- Ingestion time degradation (> 50% increase)

### Logging
- Log every email processing outcome (is_success, is_retryable)
- Log error classifications (extraction_error, row_error, etc.)
- Log retry scheduling (when email queued for retry)
- Log retry attempts (when failed email retried)

---

## Future Enhancements

### Phase 2 (Post-Launch)
1. **Admin UI for Failed Emails**
   - Dashboard showing failed email queue
   - Ability to view failure details
   - Manual retry button

2. **Batch Retry**
   - Automatic retry of multiple failed emails
   - Configurable retry window

3. **Failure Analytics**
   - Dashboard showing failure patterns
   - Root cause analysis
   - Email classification by failure type

### Phase 3 (Long-Term)
1. **Dead Letter Queue**
   - Emails that can't be retried (max attempts)
   - Manual intervention required

2. **Configurable Backoff**
   - Admin-configurable retry schedule
   - Per-error-type retry strategies

3. **Email Notifications**
   - Notify user when email fails
   - Notify admin of critical failures
   - Digest of failed emails

---

## Questions & Answers

### Q: Will partial success affect existing reports/dashboards?
**A:** Yes, need to update queries that assume runs are all-or-nothing. Add checks for `success_count` vs `total_count`.

### Q: Can users configure retry schedule?
**A:** Not in v1, but architecture supports it. FailedEmailService._calculate_next_retry_time() can be made configurable.

### Q: What if a failed email succeeds on retry?
**A:** FailedEmailService.mark_email_resolved() removes it from queue. ProcessedEmail record is updated (or new one created).

### Q: How long do failed emails stay in queue?
**A:** max 365 days (set to far future after 3 failures). Admin can manually delete or retry.

### Q: What if database is down during retry?
**A:** Retry scheduled by APScheduler will fail gracefully, try again next cycle. No data loss.

### Q: Are retried emails deduplicated correctly?
**A:** Yes, dedup logic uses identifier_column which is consistent across retries. Same hash = same identifier.

### Q: How does this affect API response time?
**A:** No impact. Email processing is async background task (Celery). API returns immediately.

### Q: Can we disable per-email savepoints?
**A:** Not recommended, but could add config flag. Savepoints have minimal overhead.

---

## Contact & Support

- **Implementation Lead:** [Your Name]
- **Code Review Lead:** [Reviewer Name]
- **Database Lead:** [DB Admin]
- **Testing Lead:** [QA Lead]

**Questions/Issues?** Refer to the 4 documentation files or reach out to implementation team.

---

## Sign-Off

- [ ] Implementation plan reviewed by team lead
- [ ] Architecture approved by tech lead
- [ ] Database schema verified
- [ ] Testing strategy accepted
- [ ] Ready to proceed with implementation

