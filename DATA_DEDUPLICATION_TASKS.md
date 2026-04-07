# Implementation Tasks: Data Deduplication, Normalization & Metrics Delta Calculation

**Feature**: Data quality enhancement through intelligent deduplication and metrics normalization  
**Status**: Ready for Implementation  
**Date Created**: 2026-04-06  
**Total Tasks**: 48  

---

## User Stories & Priorities

| Story | Title | Priority | Status |
|-------|-------|----------|--------|
| US1 | Database Schema & Deduplication Tracking | P1 | Pending |
| US2 | Text Cleaning & Deterministic UUID Generation | P1 | Pending |
| US3 | Schema Mapping UI: Metrics Toggle & DateTime Split | P1 | Pending |
| US4 | Duplicate Detection & Delta Calculation Engine | P1 | Pending |
| US5 | Integration with All Adaptors | P2 | Pending |
| US6 | Deduplication Audit & Run History UI | P2 | Pending |

---

## Phase 1: Setup & Infrastructure

**Goal**: Establish project structure and shared utilities  
**Completion Criteria**: All infrastructure components ready for feature development

- [ ] T001 Create database migration file for ingestion_deduplication table at `backend/alembic/versions/019_add_deduplication_tracking.py`
- [ ] T002 Create deduplication service module at `backend/src/app/services/deduplication_service.py`
- [ ] T003 Create text cleaning utility module at `backend/src/app/utils/text_cleaner.py`
- [ ] T004 Create UUID hashing utility module at `backend/src/app/utils/uuid_hasher.py`
- [ ] T005 Update schema mapping models at `backend/src/app/models/schema_mapping.py` to add is_metric and datetime_split fields

---

## Phase 2: Foundational Components (Blocking Prerequisites)

**Goal**: Build core deduplication infrastructure needed by all user stories  
**Completion Criteria**: Utilities tested and ready for use; database schema deployed

### Text Cleaning Utility

- [ ] T006 [P] Implement text cleaning function in `backend/src/app/utils/text_cleaner.py`:
  - Strip whitespace
  - Lowercase conversion
  - Remove special characters (keep alphanumeric + spaces)
  - Unicode NFKD normalization
  - Collapse multiple spaces
  - Unit tests with edge cases

- [ ] T007 [P] Implement text cleaning integration test in `backend/tests/unit/test_text_cleaner.py`

### UUID Hashing Utility

- [ ] T008 [P] Implement deterministic SHA256 hashing in `backend/src/app/utils/uuid_hasher.py`:
  - Take first 150 characters of cleaned text
  - Generate SHA256 hash
  - Convert to standard UUID format
  - Return both hex and UUID representations

- [ ] T009 [P] Implement UUID hashing unit tests in `backend/tests/unit/test_uuid_hasher.py`
  - Test determinism (same input → same output)
  - Test 150-char truncation
  - Test edge cases (empty, special chars, unicode)

### Database Migration

- [ ] T010 [P] Implement ingestion_deduplication table migration in `backend/alembic/versions/019_add_deduplication_tracking.py`:
  - Columns: id, run_id, row_number, cleaned_identifier, beast_uuid, is_duplicate, duplicate_of_run_id, dedup_action, metrics_calculation_summary, created_at, updated_at
  - Foreign key constraints to IngestionTaskRun
  - Indexes: (run_id, row_number), (beast_uuid), (is_duplicate)

- [ ] T011 [P] Run migration and verify table creation: `alembic upgrade head`

- [ ] T012 [P] Create ORM model for ingestion_deduplication in `backend/src/app/models/ingestion_task.py`:
  - Map all columns with proper types
  - Add relationships to IngestionTaskRun
  - Add repr and validation methods

### Schema Mapping Extensions

- [ ] T013 [P] Extend SchemaMappingField model in `backend/src/app/models/schema_mapping.py`:
  - Add `is_metric` boolean field (default: False)
  - Add `is_datetime_split` boolean field (default: False)
  - Add `datetime_split_companion_field` varchar field (nullable)
  - Add database migration for new columns

- [ ] T014 [P] Update SchemaMappingResponse schema in `backend/src/app/schemas/schema_mapping.py`:
  - Add is_metric field to response
  - Add datetime_split configuration object
  - Update validation

---

## Phase 3: User Story 1 - Database & Deduplication Service

**Goal**: Implement deduplication service that tracks duplicate detection and delta calculations  
**Acceptance Criteria**:
- ✅ Can create deduplication records for new rows
- ✅ Can query for existing duplicates by beast_uuid
- ✅ Can calculate metrics deltas correctly
- ✅ Audit trail complete and queryable

### Deduplication Service Implementation

- [ ] T015 [US1] Implement DeduplicationService class in `backend/src/app/services/deduplication_service.py`:
  - Constructor: `__init__(self, db: AsyncSession, task_id: UUID)`
  - Method: `record_new_row(row_number: int, identifier: str, is_duplicate: bool)` → stores cleaned_identifier and beast_uuid
  - Method: `find_duplicate(cleaned_identifier: str)` → returns list of previous runs with same beast_uuid
  - Method: `calculate_delta(new_value: float, previous_run_ids: list[UUID], metric_field: str)` → returns delta
  - Method: `record_dedup_action(run_id: UUID, row_number: int, action: str, calculation_summary: dict)` → stores action and metrics summary

- [ ] T016 [US1] Create DeduplicationService unit tests in `backend/tests/unit/test_deduplication_service.py`:
  - Test new row recording
  - Test duplicate finding
  - Test delta calculation accuracy
  - Test metrics summary storage
  - Test with multiple previous imports (3+ duplicates)

- [ ] T017 [US1] Implement deduplication query methods in `backend/src/app/services/deduplication_service.py`:
  - `get_deduplication_summary(run_id: UUID)` → returns counts (total_rows, total_duplicates, total_deltas)
  - `get_dedup_history(task_id: UUID, limit: int = 50)` → paginated audit log
  - `get_duplicate_chain(beast_uuid: str)` → returns all related rows across runs

- [ ] T018 [US1] Integrate DeduplicationService into IngestionService at `backend/src/app/services/ingestion_service.py`:
  - Constructor: add dedup_service parameter
  - Call record_new_row() for each processed row
  - Call find_duplicate() during row deduplication check
  - Call calculate_delta() for metric columns
  - Store results in ingestion_deduplication table

---

## Phase 4: User Story 2 - Text Cleaning & UUID Generation

**Goal**: Implement text normalization pipeline applied to all ingested data  
**Acceptance Criteria**:
- ✅ All text fields cleaned consistently
- ✅ Deterministic UUIDs generated correctly
- ✅ Special characters and unicode handled properly
- ✅ First 150 characters used for hashing

### Text Cleaning Pipeline

- [ ] T019 [US2] Implement TextCleaningService in `backend/src/app/services/text_cleaning_service.py`:
  - Class: `TextCleaner`
  - Method: `clean(text: str) → str` (applies all cleaning steps)
  - Method: `clean_and_hash(text: str) → tuple[str, str]` (returns cleaned text + beast_uuid)
  - Applied to all text fields during ingestion

- [ ] T020 [US2] [P] Integrate text cleaning into ingestion pipeline:
  - Update GmailAdapter in `backend/src/app/adapters/gmail_adapter.py` to clean extracted emails
  - Update WebhookAdapter in `backend/src/app/adapters/webhook_adapter.py` to clean webhook data
  - Update FileUploadService in `backend/src/app/services/file_storage_service.py` to clean uploaded data
  - Each adapter applies text cleaner to text fields

- [ ] T021 [US2] [P] Create integration tests for text cleaning across adaptors in `backend/tests/integration/test_text_cleaning_integration.py`:
  - Test Gmail adapter text cleaning
  - Test Webhook adapter text cleaning  
  - Test File upload text cleaning
  - Verify deterministic hashing

- [ ] T022 [US2] Add text cleaning configuration options in `backend/src/app/config.py`:
  - TEXT_CLEANING_ENABLED (boolean, default: True)
  - IDENTIFIER_HASH_LENGTH (integer, default: 150)
  - CHARACTER_WHITELIST (regex pattern for allowed characters)

---

## Phase 5: User Story 3 - Schema Mapping UI Updates

**Goal**: Add UI controls for metrics toggling and datetime field splitting  
**Acceptance Criteria**:
- ✅ "Is Metric" toggle visible and persists
- ✅ Datetime split configuration works end-to-end
- ✅ Schema mapping stores and retrieves settings
- ✅ Settings display in UI on load

### Backend Schema Mapping Endpoints

- [ ] T023 [US3] [P] Create/Update SchemaMappingField endpoints in `backend/src/app/api/admin_ingestion.py`:
  - PATCH `/api/v1/admin/ingestion/tasks/{task_id}/schema-mapping/fields/{field_id}` → update is_metric and datetime_split settings
  - Validate metric column values (numeric type or acceptable)
  - Validate datetime split companion field names

- [ ] T024 [US3] [P] Implement schema mapping service methods in `backend/src/app/services/schema_mapping_service.py`:
  - `update_field_metrics(task_id, field_id, is_metric)` → persist toggle state
  - `configure_datetime_split(task_id, field_id, companion_field_name)` → setup split fields
  - `get_metrics_columns(task_id)` → return list of metric field names
  - `get_datetime_splits(task_id)` → return datetime split configurations

### Frontend UI Components

- [ ] T025 [US3] [P] Create MetricsToggle component in `frontend/components/admin/MetricsToggle.tsx`:
  - Toggle button for marking column as metric
  - Tooltip explanation
  - Visual indication when enabled
  - OnChange callback to save to backend

- [ ] T026 [US3] [P] Create DatetimeSplitConfig component in `frontend/components/admin/DatetimeSplitConfig.tsx`:
  - Input for companion field name
  - Validation (field name must be valid)
  - Display current split configuration
  - OnChange callback to save to backend

- [ ] T027 [US3] [P] Update SchemaMapper component in `frontend/components/admin/SchemaMapper.tsx`:
  - Add MetricsToggle to each field row
  - Add DatetimeSplitConfig for datetime fields
  - Pass is_metric and datetime_split to schema submission
  - Load and display existing settings on mount

- [ ] T028 [US3] Create end-to-end test for schema mapping in `frontend/tests/e2e/schema-mapping-metrics.test.tsx`:
  - Create schema mapping
  - Toggle metrics on/off
  - Configure datetime split
  - Verify settings persist and load correctly

---

## Phase 6: User Story 4 - Duplicate Detection & Delta Calculation

**Goal**: Implement core deduplication logic with metrics delta calculation  
**Acceptance Criteria**:
- ✅ Duplicates detected by beast_uuid match
- ✅ Deltas calculated correctly for metric columns
- ✅ New rows inserted with delta values
- ✅ Audit trail shows deduplication action
- ✅ Works with 2+, 3+, many duplicates

### Deduplication Engine

- [ ] T029 [US4] Implement duplicate detection logic in `backend/src/app/services/ingestion_service.py`:
  - For each row: extract identifier → clean → hash to beast_uuid
  - Query ingestion_deduplication for matching beast_uuid
  - Return list of previous rows with same UUID (across all previous runs of task)

- [ ] T030 [US4] Implement delta calculation engine in `backend/src/app/services/ingestion_service.py`:
  - When duplicate found:
    - Identify metric columns from schema mapping
    - For each metric: calculate delta = new_value - sum(all_previous_values)
    - Return delta values and calculation summary
  - Non-metric columns: use most recent value
  - Handle missing/null values gracefully

- [ ] T031 [US4] Implement row insertion logic with deduplication in `backend/src/app/services/ingestion_service.py`:
  - If first occurrence (no duplicate): insert row as-is, mark is_duplicate=false
  - If duplicate: calculate deltas, insert new row with delta values, mark is_duplicate=true
  - Store calculation summary in metrics_calculation_summary field
  - Update run statistics (total_deduplicated, total_deltas_calculated)

- [ ] T032 [US4] Create deduplication calculation unit tests in `backend/tests/unit/test_delta_calculation.py`:
  - Test 2-duplicate case (simple delta)
  - Test 3-duplicate case (cumulative delta)
  - Test many duplicates (10+)
  - Verify sum accuracy: sum(deltas) + first_value = latest_value
  - Test various numeric types (int, float, decimal)

- [ ] T033 [US4] Create deduplication integration tests in `backend/tests/integration/test_deduplication_flow.py`:
  - Test complete flow: upload → detect duplicate → calculate delta → insert
  - Multi-import scenario (3 sequential imports of same data)
  - Verify audit trail completeness
  - All metrics calculated correctly

---

## Phase 7: User Story 5 - Integration with All Adaptors

**Goal**: Apply deduplication to all data source types  
**Acceptance Criteria**:
- ✅ Gmail ingestion deduplicates correctly
- ✅ Webhook ingestion deduplicates correctly
- ✅ File upload ingestion deduplicates correctly
- ✅ All adaptors use same deduplication pipeline

### Adaptor Integration

- [ ] T034 [US5] [P] Integrate deduplication into Gmail ingestion in `backend/src/app/services/ingestion_service.py`:
  - Method `_ingest_from_gmail_task()`: apply text cleaning to email data
  - Apply deduplication pipeline to extracted emails
  - Store deduplication records
  - Handle duplicate emails from same/different runs

- [ ] T035 [US5] [P] Integrate deduplication into Webhook ingestion in `backend/src/app/services/ingestion_service.py`:
  - Method `_ingest_from_webhook_task()`: apply text cleaning to webhook payload
  - Apply deduplication pipeline to webhook data
  - Store deduplication records
  - Handle duplicate webhook payloads

- [ ] T036 [US5] [P] Integrate deduplication into File upload ingestion in `backend/src/app/services/ingestion_service.py`:
  - Method `_ingest_from_file_upload_task()`: apply text cleaning to file data
  - Apply deduplication pipeline to CSV/Excel rows
  - Store deduplication records
  - Handle duplicate file rows

- [ ] T037 [US5] Create cross-adaptor integration tests in `backend/tests/integration/test_dedup_cross_adaptor.py`:
  - Test Gmail deduplication end-to-end
  - Test Webhook deduplication end-to-end
  - Test File upload deduplication end-to-end
  - Verify all adaptors produce consistent results

- [ ] T038 [US5] Add deduplication feature flag in `backend/src/app/models/ingestion_task.py`:
  - Add field: `deduplication_enabled` (boolean, default: True)
  - Add field: `dedup_lookback_imports` (integer, default: unlimited)
  - Update API endpoint to allow enabling/disabling per task

---

## Phase 8: User Story 6 - Audit & Run History UI

**Goal**: Display deduplication results and audit trail in UI  
**Acceptance Criteria**:
- ✅ Run history shows deduplication summary
- ✅ Audit log displays all deduplication actions
- ✅ Users can trace every deduplication decision
- ✅ Delta calculations visible for verification

### Backend Audit Endpoints

- [ ] T039 [US6] Create deduplication audit endpoints in `backend/src/app/api/admin_ingestion.py`:
  - GET `/api/v1/admin/ingestion/tasks/{task_id}/runs/{run_id}/deduplication-summary` → dedup stats
  - GET `/api/v1/admin/ingestion/tasks/{task_id}/runs/{run_id}/deduplication-log` → audit trail
  - GET `/api/v1/admin/ingestion/tasks/{task_id}/deduplication-chains` → duplicate tracking across runs

- [ ] T040 [US6] Implement audit response schemas in `backend/src/app/schemas/ingestion.py`:
  - `DeduplicationSummaryResponse`: total_rows, total_duplicates, total_deltas_calculated
  - `DeduplicationLogEntryResponse`: beast_uuid, row_number, action, calculation_summary, timestamp
  - `DeduplicationChainResponse`: related rows showing delta chain

### Frontend UI Components

- [ ] T041 [US6] [P] Create DeduplicationSummary component in `frontend/components/admin/DeduplicationSummary.tsx`:
  - Display summary stats (X rows deduplicated, Y deltas calculated)
  - Show deduplication status per run
  - Link to detailed audit log

- [ ] T042 [US6] [P] Create DeduplicationAuditLog component in `frontend/components/admin/DeduplicationAuditLog.tsx`:
  - Paginated list of deduplication actions
  - Show: row_number, beast_uuid, action, calculation_summary
  - Expandable details showing delta calculation breakdown
  - Filter by action type (first_occurrence, inserted_delta, skipped)

- [ ] T043 [US6] [P] Update TaskRunHistory in `frontend/components/admin/TaskRunHistory.tsx`:
  - Add deduplication summary column to run table
  - Show "X deduplicated, Y deltas" as clickable link
  - Modal or tab to show detailed audit log

- [ ] T044 [US6] [P] Create DeduplicationChainViewer component in `frontend/components/admin/DeduplicationChainViewer.tsx`:
  - Show duplicate tracking across imports
  - Display: original value → delta → cumulative
  - Verify sum equation: sum(deltas) + first_value = latest_value

- [ ] T045 [US6] Create integration tests for audit UI in `frontend/tests/integration/dedup-audit-ui.test.tsx`:
  - Test deduplication summary display
  - Test audit log pagination
  - Test calculation breakdown display

---

## Phase 9: Polish & Cross-Cutting Concerns

**Goal**: Complete final refinements, documentation, and testing  
**Completion Criteria**: Production-ready feature with documentation

### Documentation & Testing

- [ ] T046 [P] Create deduplication architecture document at `backend/docs/DEDUPLICATION_ARCHITECTURE.md`:
  - Overall flow diagram
  - Component interactions
  - Data models and relationships
  - Example scenarios

- [ ] T047 [P] Update backend README with deduplication configuration at `backend/README.md`:
  - Feature flag usage
  - Configuration options
  - Troubleshooting guide

- [ ] T048 [P] Create end-to-end deduplication tests in `backend/tests/e2e/deduplication_flow.py`:
  - Full import scenario with duplicates
  - Multi-adaptor testing
  - Verify audit trail completeness
  - Performance testing with 10,000+ rows

---

## Implementation Strategy

### MVP (Minimum Viable Product)
**Focus**: Core deduplication with metrics delta calculation  
**Scope**: Phases 1-4 (Database, Text Cleaning, Schema UI, Duplicate Detection)  
**Estimated Effort**: 2-3 weeks  
**User Value**: Basic duplicate detection and delta calculation working

**Task Sequence**:
1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T014)
3. Complete Phase 3: Deduplication Service (T015-T018)
4. Complete Phase 4: Text Cleaning (T019-T022)
5. Complete Phase 5 Partial: Schema UI backend only (T023-T024)

### Phase 2 Enhancement
**Add**: Full UI, additional adaptors  
**Scope**: Phases 5-6  
**Estimated Effort**: 1-2 weeks  
**User Value**: Full feature with UI and audit trail

### Phase 3 Polish
**Add**: Documentation, testing, optimization  
**Scope**: Phase 9  
**Estimated Effort**: 3-5 days  
**User Value**: Production-ready, documented

---

## Dependency Graph

```
Phase 1 (Setup)
├── Phase 2 (Foundational - BLOCKING)
│   ├── Phase 3 (US1: Dedup Service) ✓ Independent
│   ├── Phase 4 (US2: Text Cleaning) ✓ Independent
│   ├── Phase 5 (US3: Schema UI) → Requires US1 Status
│   ├── Phase 6 (US4: Delta Engine) → Requires US1, US2, US3
│   ├── Phase 7 (US5: Adaptor Integration) → Requires US4
│   └── Phase 8 (US6: Audit UI) → Requires US4
└── Phase 9 (Polish) → Requires all phases
```

**Parallelizable Tasks**:
- Phase 1: All tasks can run in parallel (T001-T005)
- Phase 2: All tasks can run in parallel (T006-T014)
- Phase 3: Most tasks can run in parallel (T015, T016, T017)
- Phase 4: T020, T021 can run in parallel with T019
- Phase 5: T034-T036 can run in parallel
- Phase 6: T041-T044 can run in parallel
- Phase 9: All documentation tasks parallelizable

---

## Independent Test Criteria by User Story

### US1: Deduplication Service
- [ ] Can create and retrieve deduplication records
- [ ] Duplicate finding works across multiple imports
- [ ] Delta calculation mathematically correct (spot check 10+ examples)
- [ ] Audit trail complete with all fields populated

### US2: Text Cleaning & UUID Generation
- [ ] All text fields cleaned consistently
- [ ] Special characters removed correctly
- [ ] Unicode normalized properly
- [ ] Beast UUID deterministic (same input = same hash)

### US3: Schema Mapping UI
- [ ] Metrics toggle persists and loads correctly
- [ ] DateTime split configuration works end-to-end
- [ ] Settings display properly in edit mode
- [ ] Non-metric fields unaffected by toggle

### US4: Duplicate Detection & Delta Calculation
- [ ] Duplicates detected by beast_uuid match
- [ ] Delta calculated with correct formula
- [ ] Single duplicate processed correctly
- [ ] Multiple duplicates (3+) processed correctly
- [ ] Sum equation verified: Σ(deltas) + first_value = latest_value

### US5: All Adaptors Integration
- [ ] Gmail ingestion deduplicates
- [ ] Webhook ingestion deduplicates
- [ ] File upload ingestion deduplicates
- [ ] Deduplication works consistently across all adaptors

### US6: Audit & History UI
- [ ] Deduplication summary displays in run history
- [ ] Audit log shows all deduplication actions
- [ ] Delta calculation breakdowns visible
- [ ] Duplicate chain tracking visible

---

**Total Estimated Timeline**:
- MVP (Phases 1-4): 2-3 weeks
- Full Feature (Phases 1-8): 3-4 weeks
- Production Ready (Phases 1-9): 4-5 weeks

