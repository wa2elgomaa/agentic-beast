# Gmail Credential Management - Testing Guide

## Overview
This document provides comprehensive testing guidance for the Gmail credential management system, including token refresh, credential status tracking, and admin UI functionality.

## System Components Tested

### Backend Components
- **GmailCredentialService**: Credential lifecycle management (8 methods)
- **GmailAdapter**: Token refresh with retry logic and error handling
- **IngestionService**: Error categorization and credential status updates
- **Admin API**: 4 new endpoints for credential management
- **Database**: Credential status and audit log tables

### Frontend Components
- **GmailCredentialStatus.tsx**: Status display and management UI
- **TaskRunHistory**: Error type badges and error codes
- **TaskDetailPage**: Gmail credentials tab

---

## Test Scenarios

### 1. Initial Authentication (Happy Path)
**Objective**: Verify successful Gmail authentication sets up credential tracking

**Steps**:
1. Create new Gmail ingestion task
2. Click "Authenticate Gmail"
3. Complete OAuth flow with valid Google account
4. Verify redirect back to task detail page

**Expected Results**:
- ✅ OAuth code exchanged for access/refresh tokens
- ✅ Tokens stored in `ingestion_tasks.adaptor_config["gmail_oauth"]`
- ✅ `GmailCredentialStatus` record created with status="active"
- ✅ `GmailCredentialAuditLog` entry: event_type="authenticated"
- ✅ Account email captured in credential_status table
- ✅ health_score=100, consecutive_failures=0
- ✅ auth_established_at timestamp set
- ✅ Gmail Credentials tab visible on task detail page
- ✅ Tab shows: status="active", account_email populated, health_score bar at 100%

**API Calls**:
- `POST /admin/ingestion/tasks/{id}/gmail/auth-url`: Get OAuth URL
- `POST /admin/ingestion/tasks/{id}/gmail/exchange-code`: Exchange code for tokens
- `GET /admin/ingestion/tasks/{id}/gmail/credential-status`: Verify status

---

### 2. Successful Ingestion (Credential Health)
**Objective**: Verify successful ingestion updates credential health tracking

**Preconditions**:
- Gmail task with active credentials
- Valid Gmail account to inbox

**Steps**:
1. Configure task with Gmail inbox as source
2. Set up schema mapping to extract emails
3. Trigger ingestion task run
4. Verify run completes successfully

**Expected Results**:
- ✅ Ingestion queries emails from Gmail inbox
- ✅ Task status marked as COMPLETED
- ✅ `GmailCredentialStatus.last_used_at` updated to current timestamp
- ✅ `GmailCredentialStatus.consecutive_failures` remains 0
- ✅ `GmailCredentialStatus.health_score` remains 100
- ✅ `GmailCredentialAuditLog` entry: event_type="token_refreshed" (if token was refreshed)
- ✅ Rows inserted/updated correctly
- ✅ Run shows status="completed", rows_inserted>0, error_type=null, error_code=null

**Validation**:
```sql
-- Query credential status
SELECT status, health_score, consecutive_failures, last_used_at 
FROM gmail_credential_status 
WHERE task_id = '{task_id}';
-- Expected: active | 100 | 0 | <recent timestamp>

-- Query run result
SELECT status, rows_inserted, error_type, error_code 
FROM ingestion_task_runs 
WHERE task_id = '{task_id}' 
ORDER BY created_at DESC LIMIT 1;
-- Expected: completed | >0 | null | null
```

---

### 3. Token Expiration Handling (Invalid Grant)
**Objective**: Verify system correctly handles invalid_grant errors and marks credentials as invalid

**Preconditions**:
- Gmail task with valid credentials
- Access to revoke OAuth token in Google Account

**Steps**:
1. Complete successful ingestion (from Scenario 2)
2. Go to Google Account settings → Connected apps
3. Revoke access for this app
4. Attempt to trigger new ingestion
5. Observe error handling

**Expected Results**:
- ✅ Adapter.connect() catches RefreshError with "invalid_grant"
- ✅ Raises `CredentialExpiredError` exception
- ✅ IngestionService catches exception, sets:
  - error_type="auth_error"
  - error_code="invalid_grant"
  - status=FAILED
- ✅ `GmailCredentialStatus` updated:
  - status → "invalid"
  - last_error_code → "invalid_grant"
  - last_error_message → error description from Google
  - consecutive_failures → 1 (or incremented)
  - health_score → degraded (e.g., 70 or 50 depending on failures)
- ✅ `GmailCredentialAuditLog` entry: event_type="auth_failed"
- ✅ Run marked as FAILED with 0 rows processed
- ✅ Error shown in UI

**UI Verification**:
- Go to task detail page → Gmail Credentials tab
- ✅ Status badge shows: INVALID (red background)
- ✅ Health score bar shows degraded value
- ✅ Error alert displays:
  - Last Error: invalid_grant
  - Error message from Google
- ✅ "Re-authenticate" button is highlighted/available
- ✅ Audit log shows auth_failed event

**API Response**:
```bash
GET /admin/ingestion/tasks/{id}/gmail/credential-status
{
  "status": "invalid",
  "health_score": 50,
  "consecutive_failures": 1,
  "last_error_code": "invalid_grant",
  "last_error_message": "Token has been revoked."
}
```

---

### 4. Transient Error Retry (Network Timeout)
**Objective**: Verify system retries transient errors and recovers

**Preconditions**:
- Gmail task with valid credentials
- Network simulation tool (e.g., tc on Linux, or intentional mock timeout)

**Setup** (Simulated):
- Modify test to mock Google API timeout on first 2 calls
- Third call succeeds

**Expected Results**:
- ✅ Adapter.connect() catches RefreshError (not invalid_grant)
- ✅ Implements exponential backoff:
  - Attempt 1: Fails, sleep 2^0=1 second
  - Attempt 2: Fails, sleep 2^1=2 seconds
  - Attempt 3: Succeeds
- ✅ Does NOT mark credential as invalid
- ✅ `GmailCredentialStatus` NOT updated (transient, not permanent)
- ✅ Raises `TemporaryAuthError`
- ✅ IngestionService catches, sets error_type="network_error"
- ✅ Run marked as FAILED (0 rows)
- ✅ Allows manual retry without re-authentication

**Validation**:
- Credential status remains ACTIVE
- Consecutive failures NOT incremented (transient)
- Error code shows "temporary_auth_failure"

---

### 5. Credential Clear (Admin Action)
**Objective**: Verify admin can manually clear credentials

**Preconditions**:
- Gmail task with active or invalid credentials

**Steps**:
1. Go to task detail page → Gmail Credentials tab
2. Click "Clear Credentials" button
3. Confirm dialog
4. Observe page update

**Expected Results**:
- ✅ HTTP DELETE to `/admin/ingestion/tasks/{id}/gmail/credentials`
- ✅ `ingestion_tasks.adaptor_config["gmail_oauth"]` deleted
- ✅ `GmailCredentialStatus` updated:
  - status → "pending_auth"
  - consecutive_failures → 0
  - account_email → NULL
  - error fields cleared
- ✅ `GmailCredentialAuditLog` entry: event_type="manually_cleared"
- ✅ action_by field set to admin user ID
- ✅ UI shows status="pending_auth"
- ✅ "Re-authenticate" button highlighted
- ✅ Account email shows as "-"
- ✅ Health score bar at 100%

**Database Validation**:
```sql
SELECT status, account_email, consecutive_failures, last_error_code 
FROM gmail_credential_status 
WHERE task_id = '{task_id}';
-- Expected: pending_auth | null | 0 | null
```

---

### 6. Credential Audit Log History
**Objective**: Verify complete audit trail of credential events

**Preconditions**:
- Gmail task that went through scenarios 1-5

**Steps**:
1. Go to task detail page → Gmail Credentials tab
2. Click on "Credential History" to expand audit log
3. Review all events

**Expected Results**:
- ✅ Audit log shows events in reverse chronological order:
  - manually_cleared (with cleared_by=admin_id)
  - auth_failed with error_code
  - token_refreshed (from scenario 2)
  - authenticated (from scenario 1)
- ✅ Each event shows:
  - Timestamp
  - Event type
  - Account email (if applicable)
  - Error code (if applicable)
  - Error message (if applicable)
- ✅ Admin user ID shown for manual actions
- ✅ Automatic actions (token_refreshed) show action_by=NULL

**API Response**:
```bash
GET /admin/ingestion/tasks/{id}/gmail/audit-log?limit=50
{
  "audit_log": [
    {
      "id": "...",
      "event_type": "manually_cleared",
      "created_at": "2026-04-06T...",
      "action_by": "{admin_user_id}"
    },
    {
      "id": "...",
      "event_type": "auth_failed",
      "error_code": "invalid_grant",
      "error_message": "Token has been revoked.",
      "created_at": "2026-04-06T..."
    },
    ...
  ],
  "total": 4,
  "limit": 50,
  "offset": 0
}
```

---

### 7. Re-authentication Flow
**Objective**: Verify admin can re-authenticate after credential failure

**Preconditions**:
- Gmail task with invalid credentials (from Scenario 3)
- Status shows "invalid"

**Steps**:
1. Go to task detail page → Gmail Credentials tab
2. Click "Re-authenticate" button
3. Complete OAuth flow in new window
4. Return to task page
5. Observe status update

**Expected Results**:
- ✅ "Re-authenticate" button redirects to Google OAuth
- ✅ User completes consent flow
- ✅ Backend exchanges code for new tokens
- ✅ `GmailCredentialStatus` updated:
  - status → "active"
  - consecutive_failures → 0
  - health_score → 100
  - auth_established_at → current timestamp
  - error fields cleared
- ✅ `GmailCredentialAuditLog` entry: event_type="authenticated"
- ✅ New tokens stored in adaptor_config
- ✅ UI refreshes to show:
  - Status badge: ACTIVE (green)
  - Health score: 100%
  - Last error cleared
- ✅ Next ingestion succeeds

---

### 8. Error Type Categorization in Run History
**Objective**: Verify run history displays error types and codes

**Preconditions**:
- Multiple task runs with different error types

**Steps**:
1. Go to task detail page → Run History tab
2. Observe run history table

**Expected Results**:
- ✅ Run with status=COMPLETED shows:
  - Error column: "-"
  - No error badge
- ✅ Run with auth_error shows:
  - Error badge: "auth_error" (orange)
  - Error code badge: "invalid_grant" (gray)
  - Error message truncated
- ✅ Run with network_error shows:
  - Error badge: "network_error" (purple)
  - Error code badge: "temporary_auth_failure"
- ✅ Run with data_error shows:
  - Error badge: "data_error" (red)
- ✅ Hovering over truncated error message shows tooltip with full message

**Database Validation**:
```sql
SELECT id, status, error_type, error_code, error_message 
FROM ingestion_task_runs 
WHERE task_id = '{task_id}' 
ORDER BY created_at DESC;
```

---

### 9. Health Score Degradation
**Objective**: Verify health score degrades with consecutive failures

**Preconditions**:
- Gmail task with valid credentials
- Ability to simulate/trigger repeated auth failures

**Setup** (Mock):
- First failure: health_score should degrade
- Second failure: health_score degrades further
- Third failure (max): status should become "needs_refresh"

**Expected Results**:
- ✅ On each failure:
  ```
  failure_ratio = min(consecutive_failures / max_consecutive_failures, 1.0)
  health_score = max(0, int(100 * (1 - failure_ratio)))
  ```
  Examples with max_consecutive_failures=3:
  - 1 failure: health_score = 67
  - 2 failures: health_score = 34
  - 3 failures: health_score = 0, status = "needs_refresh"

- ✅ UI health bar reflects degradation (green → yellow → red)
- ✅ After max failures reached, status badge shows "NEEDS_REFRESH"
- ✅ Manual re-authentication resets health_score to 100

**Validation**:
```sql
SELECT consecutive_failures, health_score 
FROM gmail_credential_status 
WHERE task_id = '{task_id}';
-- Verify formula matches expected values
```

---

### 10. Failure Count Reset on Success
**Objective**: Verify consecutive failures reset after successful ingestion

**Preconditions**:
- Gmail task with consecutive_failures > 0
- Credentials fixed (e.g., re-authenticated)

**Steps**:
1. Verify credential status shows > 0 consecutive failures
2. Complete successful ingestion
3. Check credential status

**Expected Results**:
- ✅ After successful ingestion:
  - consecutive_failures → 0
  - health_score → 100
  - last_used_at → updated
  - status remains "active"
- ✅ `GmailCredentialAuditLog` entry: event_type="token_refreshed"
- ✅ UI health bar returns to full green

**Database Validation**:
```sql
-- Verify reset
SELECT consecutive_failures, health_score, last_used_at 
FROM gmail_credential_status 
WHERE task_id = '{task_id}';
-- Expected: 0 | 100 | <recent>
```

---

## Integration Test Checklist

### Backend Integration
- [ ] Database migrations run successfully
  - [ ] `gmail_credential_status` table created
  - [ ] `gmail_credential_audit_log` table created
  - [ ] Indexes created correctly
  - [ ] `ingestion_task_runs` new columns added
- [ ] ORM models import without errors
- [ ] GmailCredentialService methods callable
- [ ] GmailAdapter integration with credential service works
- [ ] IngestionService error handling integration works
- [ ] API endpoints respond with correct status codes

### Frontend Integration
- [ ] GmailCredentialStatus component renders without errors
- [ ] TaskDetailPage loads with correct tab state
- [ ] Gmail Credentials tab only appears for Gmail tasks
- [ ] TaskRunHistory displays error types correctly
- [ ] API calls to credential endpoints work
- [ ] Error handling in components works

### End-to-End Integration
- [ ] Complete flow: Auth → Ingest → Verify Status → Clear → Re-auth
- [ ] Credential status updates reflected in UI
- [ ] Audit log entries visible in UI
- [ ] Error badges display correctly in run history

---

## Deployment Checklist

- [ ] Database migrations executed in production
- [ ] Backend services deployed with new code
- [ ] Frontend assets built and deployed
- [ ] API endpoints accessible
- [ ] HTTPS enabled for OAuth redirect URIs
- [ ] Monitoring configured for credential errors
- [ ] Logging captures all credential events
- [ ] Rollback plan documented

---

## Performance Considerations

- **Credential Status Queries**: Indexed by task_id (UNIQUE), no N+1 queries
- **Audit Log Queries**: Indexed by task_id and created_at for pagination
- **Token Refresh**: Happens before ingestion, fail-fast pattern prevents partial ingestion
- **Health Score Calculation**: O(1) arithmetic operation
- **Audit Log Retention**: Consider archiving old entries (>6 months) to prevent table bloat

---

## Security Considerations

- ✅ Refresh tokens stored in encrypted database column (via SQLAlchemy)
- ✅ Access tokens in memory only (not logged)
- ✅ Audit log tracks who cleared credentials
- ✅ Admin-only endpoints protected (get_current_admin dependency)
- ✅ Error messages don't leak sensitive data
- ✅ OAuth state parameter used to prevent CSRF
- ⚠️ TODO: Consider token encryption at rest for maximum security

---

## Troubleshooting Guide

### Symptom: "Credential status not found"
- **Cause**: Task created before new code deployed
- **Solution**: Access endpoint, will auto-create status record via `get_or_create`

### Symptom: "Token invalid_grant but status still shows active"
- **Cause**: Cache issue or stale page
- **Solution**: Refresh credential status via API or page reload

### Symptom: "Retries taking too long"
- **Cause**: Exponential backoff configured too aggressively
- **Adjustment**: If 2^0 + 2^1 = 3 seconds too long, reduce max_retries or backoff factor

### Symptom: "Health score not degrading"
- **Cause**: consecutive_failures not being incremented
- **Debug**: Check ingestion_service error handling and verify exception being raised

---

## Documentation References

- Database Schema: See `018_add_gmail_credential_tracking.py` migration
- API Endpoints: See `backend/src/app/api/admin_ingestion.py` routes
- Service Methods: See `backend/src/app/services/gmail_credential_service.py`
- Error Handling: See `backend/src/app/adapters/gmail_adapter.py`
