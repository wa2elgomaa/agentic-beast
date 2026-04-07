# Feature Specification: Data Deduplication, Normalization & Metrics Delta Calculation

**Status**: Draft  
**Created**: 2026-04-06  
**Feature**: Data quality enhancement through intelligent deduplication and metrics normalization

---

## Overview

Implement intelligent row deduplication with automatic metrics delta calculation. When duplicate records are detected (based on cleaned identifier), the system will:
- Extract and normalize metrics columns (subtracting previous values)
- Split datetime fields into separate date and time columns
- Generate deterministic UUIDs for tracking and matching
- Apply consistent text cleaning across all text fields

This ensures clean, non-duplicate data with properly normalized metrics that reflect actual changes.

---

## User Value Proposition

**For Data Analysts**: 
- Eliminates duplicate data entries automatically
- Transforms raw metrics into delta values (change over time)
- Enables accurate trend analysis without manual cleanup

**For Data Engineers**:
- Configurable metrics columns per task
- Deterministic UUID generation for reliable matching
- Audit trail of deduplication actions

**For Business**:
- Improved data quality and accuracy
- Reduced manual data cleaning effort
- Better metrics analysis for decision-making

---

## Functional Requirements

### 1. Schema Mapping Enhancements

**1.1 Metrics Column Marking**
- Add "Is Metric" toggle button in schema mapping UI for each mapped field
- Toggle indicates column contains numeric values that should be delta-calculated
- Non-metric columns are copied as-is to new rows
- Default: unchecked (columns are not metrics)
- User impact: Easy visual identification of metric columns

**1.2 Datetime Field Splitting**
- Support mapping datetime Excel/CSV columns to two output fields:
  - Primary field: date only (format: YYYY-MM-DD)
  - Companion field: time only (format: HH:MM:SS)
- Example: `published_date` Excel column → 
  - `published_date` output (2026-04-06)
  - `published_time` output (14:30:45)
- Remove old "Use split Date + Time columns for this field" feature
- Preserve original datetime value handling for non-split datetime fields

**1.3 Schema Mapping Persistence**
- Store "Is Metric" toggle state in schema mapping configuration
- Store datetime split configuration (which columns are split, companion field names)
- Load and display settings when editing existing mappings

### 2. Text Normalization

**2.1 Text Cleaning Function**
- Apply to all text fields during ingestion (identifier column and others)
- Cleaning steps (in order):
  1. Trim leading/trailing whitespace
  2. Convert to lowercase
  3. Remove special characters (keep alphanumeric and spaces only)
  4. Normalize unicode characters (NFKD normalization)
  5. Collapse multiple spaces to single space
- Applied consistently across all adaptors (Gmail, Webhook, File Upload, etc.)

**2.2 Identifier Column Cleaning**
- Use first 150 characters of cleaned identifier column for matching
- Hash these 150 characters using SHA256 to create `beast_uuid`
- Store both cleaned identifier and beast_uuid in deduplication tracking

### 3. Deterministic Beast UUID Generation

**3.1 SHA256 Hashing**
- Generate deterministic UUID by:
  1. Take first 150 characters of cleaned identifier column
  2. Apply SHA256 hash
  3. Convert hash to UUID format (preserve as hex or convert to proper UUID)
- Deterministic: same input always produces same beast_uuid
- Enables matching across multiple imports of same data

**3.2 Deduplication Tracking**
- Track both: cleaned identifier text AND beast_uuid
- Store in new `ingestion_deduplication` table:
  - `run_id` (foreign key to IngestionTaskRun)
  - `row_number` (position in result set)
  - `cleaned_identifier` (first 150 cleaned chars)
  - `beast_uuid` (SHA256 hash as UUID)
  - `is_duplicate` (boolean: true if row matched previous)
  - `duplicate_of_run_id` (reference to matching row from previous run)
  - `dedup_action` (e.g., "inserted_delta", "skipped_duplicate", "first_occurrence")

### 4. Row Deduplication with Metrics Delta

**4.1 Duplicate Detection**
- When processing new row: hash first 150 cleaned identifier chars
- Query `ingestion_deduplication` table for previous rows with matching beast_uuid
- If found in same run OR previous runs: mark as duplicate

**4.2 Metrics Delta Calculation**
- For duplicate rows (within same task):
  - Identify all metrics columns (marked with "Is Metric" toggle)
  - For each metric: `delta_value = new_value - sum(all_previous_values)`
  - Example:
    - Previous rows: video_views = [1000, 300]
    - New row: video_views = 1850
    - Delta: 1850 - (1000 + 300) = 550
    - INSERT: video_views = 550
  - Non-metric columns: use most recent value or skip if empty

**4.3 New Row Insertion**
- Instead of skipping/replacing, INSERT new row with:
  - Calculated delta values for metric columns
  - Most recent non-metric values
  - New timestamp/metadata
  - `dedup_action` = "inserted_delta"
- Track: which rows were combined, calculation details
- Audit trail: store sum of previous values for verification

**4.4 Deduplication Behavior**
- **First occurrence**: Insert as-is, mark `is_duplicate = false`
- **Subsequent occurrences (same task)**: Calculate delta, insert new row with delta values
- **Subsequent occurrences (different task)**: Treat as first occurrence (fresh calculation per task)
- Non-metric columns unchanged (use value from new/latest row)

### 5. Apply to All Adaptors

- Gmail adaptor: Apply deduplication to extracted email data
- Webhook adaptor: Apply deduplication to webhook payloads
- File Upload adaptor: Apply deduplication to CSV/Excel rows
- API Feed adaptor: Apply deduplication to feed entries (if applicable)
- No adaptor-specific logic: all use same cleaning & deduplication pipeline

### 6. Configuration & Control

**6.1 Task-Level Settings**
- Option to enable/disable deduplication per task (default: enabled)
- Configure lookback window (check previous N imports for duplicates? or all-time?)
- Configure which runs to check for duplicates (same import, previous N imports, all previous)

**6.2 Run History**
- Display deduplication summary in run history:
  - "X rows deduplicated, Y deltas calculated"
  - "Z rows inserted after deduplication"
- Link to deduplication audit log

---

## User Scenarios & Testing

### Scenario 1: Initial Data Upload with Metrics
**Actor**: Data analyst  
**Context**: First import of CSV with video statistics  
**Flow**:
1. Upload CSV with columns: `video_id`, `title`, `views`, `likes`
2. Map columns in schema mapping:
   - `video_id` → identifier
   - `title` → text field
   - `views` → metric (toggle ON)
   - `likes` → metric (toggle ON)
3. System processes rows:
   - Row 1: video_id=123, views=1000, likes=50 → INSERT as-is
   - Stored: beast_uuid=hash("video-123"), is_duplicate=false
4. Result: 1 row inserted, 0 deduplicated

**Test Cases**:
- ✅ "Is Metric" toggle persists in schema
- ✅ Metrics marked correctly in configuration
- ✅ First occurrence inserted without modification
- ✅ Beast UUID generated deterministically

### Scenario 2: Delta Calculation on Duplicate
**Actor**: Data analyst  
**Context**: Second import of same CSV with updated metrics  
**Flow**:
1. Re-upload CSV with same video but updated:
   - Row 1: video_id=123, views=1850, likes=100
2. System:
   - Cleans identifier: "video-123"
   - Generates beast_uuid (same as previous)
   - Finds duplicate from previous run
   - Calculates delta:
     - views_delta = 1850 - 1000 = 850
     - likes_delta = 100 - 50 = 50
   - INSERT new row: video_id=123, views=850, likes=50
   - Tracks: `dedup_action="inserted_delta"`, `duplicate_of_run_id=<prev_run>`
3. Result: 1 row inserted (delta), 1 deduplicated

**Test Cases**:
- ✅ Duplicate identified by beast_uuid match
- ✅ Delta calculated correctly
- ✅ Only delta values inserted
- ✅ Deduplication tracking recorded

### Scenario 3: Datetime Field Splitting
**Actor**: Data analyst  
**Context**: Ingesting event data with datetime  
**Flow**:
1. CSV has column: `event_time` (datetime: 2026-04-06 14:30:45)
2. Schema mapping:
   - Map `event_time` → `event_date` (date only)
   - Configure split: associate `event_time_split` → `event_time` (time only)
3. System processes:
   - `event_date` column gets: 2026-04-06
   - `event_time` column gets: 14:30:45
4. Result: Two separate columns in output

**Test Cases**:
- ✅ DateTime split into date (YYYY-MM-DD) and time (HH:MM:SS)
- ✅ Original datetime value properly parsed
- ✅ Invalid datetimes handled gracefully (fallback to original or null)

### Scenario 4: Text Cleaning & Unicode
**Actor**: System  
**Context**: Processing text with special characters  
**Flow**:
1. Input identifier: "  Video™ #123-ABC!  "
2. Cleaning applied:
   - Trim: "Video™ #123-ABC!"
   - Lowercase: "video™ #123-abc!"
   - Remove special chars: "video 123abc"
   - Normalize unicode: "video 123abc"
   - Collapse spaces: "video 123abc"
3. First 150 chars hashed to beast_uuid
4. Used for deduplication matching

**Test Cases**:
- ✅ Special characters removed correctly
- ✅ Unicode normalized
- ✅ Final cleaned text used for hashing
- ✅ Multiple identical values produce same hash

### Scenario 5: Multiple Duplicates (3+ occurrences)
**Actor**: System  
**Context**: Same row appears in 3 consecutive imports  
**Flow**:
1. Import 1: views=1000 → INSERT, is_duplicate=false
2. Import 2: views=1500 → delta=500 → INSERT, is_duplicate=true, delta=500
3. Import 3: views=1900 → delta=(1900-1000-500)=400 → INSERT, is_duplicate=true, delta=400
4. Result: 3 rows total (1 baseline + 2 deltas)

**Test Cases**:
- ✅ Each delta calculated from sum of all previous imports
- ✅ Deduplication tracking shows chain of related rows
- ✅ Metrics accumulate correctly

---

## Data Model Changes

### New Table: `ingestion_deduplication`

```
- id (UUID, primary key)
- run_id (UUID, foreign key → IngestionTaskRun)
- row_number (integer)
- cleaned_identifier (varchar 150)
- beast_uuid (varchar 64 or UUID)
- is_duplicate (boolean)
- duplicate_of_run_id (UUID, nullable, foreign key → IngestionTaskRun)
- dedup_action (enum: first_occurrence, inserted_delta, skipped)
- metrics_calculation_summary (jsonb, nullable)
  - { "views": {"previous_sum": 1300, "new_value": 1850, "delta": 550}, ... }
- created_at (timestamp)
- updated_at (timestamp)

Indexes:
- (run_id, row_number) - within run lookup
- (beast_uuid, task_id) - cross-run dedup matching
- (is_duplicate) - query for duplicates
```

### Schema Mapping Model Extensions

Add to `SchemaMappingField` or new table:
```
- id (UUID, primary key)
- mapping_id (foreign key)
- field_name (varchar)
- is_metric (boolean, default: false)
- is_datetime_split (boolean, default: false)
- datetime_split_companion_field (varchar, nullable)
  - e.g., if field is "published_date", companion is "published_time"
```

### IngestionTaskRun Extensions

Add columns for deduplication summary:
```
- total_rows_processed (integer)
- total_duplicates_found (integer)
- total_deltas_calculated (integer)
- deduplication_enabled (boolean)
```

---

## Success Criteria

1. **Functional Accuracy**
   - ✅ Delta calculation produces expected results (verified by test scenarios)
   - ✅ Beast UUID is deterministic (same input always produces same hash)
   - ✅ Duplicate detection works across multiple imports
   - ✅ Text cleaning handles special characters and unicode

2. **Data Quality**
   - ✅ Zero data loss (all duplicate rows tracked in audit log)
   - ✅ Audit trail complete (can trace every deduplication decision)
   - ✅ Metrics align correctly (sum of deltas + original = latest value)

3. **Performance**
   - ✅ Deduplication lookup completes in < 100ms per row
   - ✅ Ingestion time increases < 20% due to deduplication overhead
   - ✅ Database queries for dedup tracking use indexes efficiently

4. **Usability**
   - ✅ UI clearly shows which columns are metrics (toggle obvious)
   - ✅ Users understand datetime split configuration
   - ✅ Run history shows deduplication summary at a glance
   - ✅ Support staff can debug deduplication decisions via audit log

5. **Integration**
   - ✅ Works with all adaptor types (Gmail, Webhook, File Upload)
   - ✅ Backward compatible (existing tasks work without changes)
   - ✅ Optional per-task (can be disabled if not needed)

---

## Assumptions

1. **Metrics are numeric**: "Is Metric" columns contain numbers that can be summed
2. **Identifiers are text**: Identifier column contains text (cleaned to first 150 chars)
3. **Within-task deduplication**: Check for duplicates within the same task (may enhance to cross-task later)
4. **Text cleaning universal**: Same cleaning applied to all text fields in all adaptors
5. **Deterministic UUID stable**: Once generated, beast_uuid never changes (immutable)
6. **Datetime formats standard**: Will handle ISO8601, US formats (MM/DD/YYYY), EU formats (DD/MM/YYYY)
7. **Non-metric columns**: Use value from new/latest duplicate row (most recent wins)

---

## Known Limitations & Future Enhancements

- **Limited to numeric metrics**: Future could support percentage changes, ratio calculations
- **Linear deduplication**: Assumes linear time series; future could support windowing
- **Single task scope**: Currently per-task; future could cross-task deduplication
- **No machine learning**: Future could use similarity matching instead of exact hash matching

---

## Implementation Notes for Planning

- Database migration required (new table, schema extensions)
- Text cleaning utility function can be extracted and reused
- SHA256 hashing library available in Python (hashlib)
- Schema mapping UI needs validation for split datetime configuration
- All adaptors must pass rows through deduplication pipeline
- Celery task may need optimization for large deduplications (10,000+ rows)

---

## Questions for User Clarification

None - requirements are sufficiently detailed and unambiguous.

