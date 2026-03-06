# Feature Specification: Agentic AI Assistant Platform

**Feature Branch**: `001-agentic-ai-assistant`
**Created**: 2026-03-05
**Status**: Draft
**Input**: User description: "AI assistant platform with agentic architecture, pluggable data adaptors, analytics querying, document Q&A, tag suggestion, and article recommendation"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analytics Data Querying (Priority: P1)

A user asks the assistant natural-language questions about social media analytics data (e.g., "What was our total reach on Instagram last week?" or "Show me the top 5 posts by engagement in February"). The assistant uses a hybrid data access approach: it generates structured query objects that pre-built tool functions execute safely against the `documents` table, augmented by vector retrieval (RAG) for contextual evidence and pre-computed daily/weekly summaries for common queries. The assistant also proactively recommends optimal publishing times (best day of the week, best time slots) based on historical performance patterns in the data.

**Why this priority**: This is the core value proposition replacing the legacy SQL-generation system. Analytics querying is the most frequently used capability and the foundation all other features build on.

**Independent Test**: Can be fully tested by sending analytics questions via the chat interface and verifying correct structured query generation, tool execution, and result formatting against known data in `documents`.

**Acceptance Scenarios**:

1. **Given** analytics data exists in `documents` for the past 30 days, **When** the user asks "What was our total reach on Instagram last week?", **Then** the assistant returns the correct aggregated reach value with a date range explanation.
2. **Given** multiple platform records exist, **When** the user asks "Compare engagement rates across all platforms for January", **Then** the assistant returns a comparison with platform names, engagement metrics, and relative performance.
3. **Given** the user asks a vague analytics question like "How are we doing?", **Then** the assistant asks clarifying follow-up questions (which metric, which time period, which platform).
4. **Given** the user asks about data that does not exist (e.g., a future date), **Then** the assistant informs the user that no data is available for that period.
5. **Given** the user asks "When is the best day to publish on Instagram?", **When** sufficient historical data exists, **Then** the assistant analyzes engagement patterns by day-of-week and returns a recommendation with supporting data (e.g., "Tuesday posts average 35% higher engagement").

---

### User Story 2 - Gmail Excel Report Ingestion (Priority: P1)

An operations user configures the system to monitor a Gmail inbox for analytics report emails. When a new email arrives with an Excel attachment, the system automatically downloads the attachment, parses the spreadsheet columns, validates the data against the `documents` schema, and inserts the records into the database. The user can also trigger manual ingestion.

**Why this priority**: Without data ingestion, the analytics querying capability has no data to work with. This is the primary data pipeline and must be operational before analytics queries are useful.

**Independent Test**: Can be tested by sending a sample Excel report email to the monitored inbox and verifying records appear correctly in `documents` within the expected processing window.

**Acceptance Scenarios**:

1. **Given** a configured Gmail inbox, **When** an email arrives with an Excel attachment matching the expected format, **Then** the system extracts all rows and inserts them into `documents` with correct column mapping.
2. **Given** the same report for the same date is processed twice, **When** the second ingestion runs, **Then** existing records are updated (upserted) rather than duplicated.
3. **Given** an Excel file with missing or malformed columns, **When** the system processes it, **Then** it logs specific validation errors and skips invalid rows while processing valid ones.
4. **Given** a non-Excel attachment or an unrelated email, **When** the system encounters it, **Then** it ignores the email without errors.

---

### User Story 3 - Tag Suggestion for Articles (Priority: P2)

A content editor asks the assistant to suggest tags for a specific article by providing an article ID. The assistant fetches the article content from the CMS API, analyzes the content against the existing tags in the `tags` table (using both keyword matching and semantic similarity via embeddings), and suggests the top N most relevant tags.

**Why this priority**: Tag suggestion directly improves content organization and discoverability. It depends on the core assistant infrastructure being in place but is a high-value feature for content teams.

**Independent Test**: Can be tested by providing a known article ID and verifying the suggested tags are semantically relevant to the article content.

**Acceptance Scenarios**:

1. **Given** an article exists in the CMS with a known ID, **When** the user asks "Suggest 5 tags for article abc123", **Then** the assistant fetches the article, analyzes its content, and returns 5 tags from the `tags` table ranked by relevance with confidence scores.
2. **Given** the user specifies a custom number of tags, **When** they ask "Suggest 10 tags for article xyz", **Then** exactly 10 tags are returned.
3. **Given** an invalid article ID, **When** the user requests tag suggestions, **Then** the assistant informs the user that the article was not found.
4. **Given** the article content is in Arabic or another non-English language, **When** tag suggestions are requested, **Then** the system handles multilingual content on a best-effort basis and suggests appropriate tags where possible.

---

### User Story 4 - Related Article Recommendation (Priority: P2)

A content editor asks the assistant to find related stories for a specific article. The assistant fetches the target article content via the CMS API, then performs bulk semantic similarity search directly against MongoDB to find the top N most relevant related stories.

**Why this priority**: Article recommendation complements tag suggestion and adds significant value for content curation. It uses similar infrastructure (CMS API, semantic search) and can be developed alongside tag suggestion.

**Independent Test**: Can be tested by providing a known article ID and verifying the recommended articles are topically related.

**Acceptance Scenarios**:

1. **Given** an article exists with a known ID and the article database contains many articles, **When** the user asks "Suggest 5 related stories for article abc123", **Then** the assistant returns 5 articles with titles, IDs, and relevance explanations.
2. **Given** the user specifies a number, **When** they ask "Find 3 similar articles to xyz", **Then** exactly 3 recommendations are returned.
3. **Given** a newly published article with no close matches, **When** recommendations are requested, **Then** the assistant returns the best available matches with a note about limited similarity.

---

### User Story 5 - Company Document Q&A (Priority: P3)

An admin ingests company documents (PDFs, images, Excel files, or text files) such as HR procedures, company policies, or operational guides via either a dedicated API upload endpoint or by placing files in a watched folder. The system automatically processes new documents, chunks them, stores them with vector embeddings, and can answer natural-language questions about their content.

**Why this priority**: Document Q&A is a powerful but broader capability. It requires a robust document processing pipeline and RAG (Retrieval-Augmented Generation) infrastructure. Delivering it after analytics and content features ensures the core platform is stable.

**Independent Test**: Can be tested by uploading a sample HR policy document and asking specific questions about its content, verifying accurate answers with source citations.

**Acceptance Scenarios**:

1. **Given** an HR policy PDF has been ingested, **When** the user asks "What is the vacation policy for employees with 5+ years?", **Then** the assistant returns the relevant policy section with a reference to the source document.
2. **Given** multiple documents exist on overlapping topics, **When** the user asks a question, **Then** the assistant synthesizes information from all relevant documents and cites each source.
3. **Given** a user asks a question not covered by any ingested document, **Then** the assistant clearly states it cannot find relevant information in the company documents.

---

### User Story 6 - General Smart Assistant (Priority: P3)

When a user asks questions outside the scope of analytics, tags, articles, or company documents, the assistant responds as a general-purpose AI assistant. It can answer general knowledge questions, help with writing tasks, or provide explanations.

**Why this priority**: This is a catch-all capability that improves user experience but does not require domain-specific infrastructure. The underlying LLM provides this capability with minimal additional work.

**Independent Test**: Can be tested by asking general knowledge questions and verifying helpful, accurate responses.

**Acceptance Scenarios**:

1. **Given** the user asks "What is the capital of France?", **When** the assistant processes the query, **Then** it responds correctly without attempting to query internal databases.
2. **Given** the user asks a question that could be about internal data or general knowledge, **When** the query is ambiguous, **Then** the assistant clarifies whether the user means internal data or general information.

---

### Edge Cases

- **Gmail API token expiry**: The Gmail adapter MUST detect OAuth2 token expiry errors, attempt automatic refresh using the stored refresh token, and log a structured alert if refresh fails. Ingestion pauses until credentials are restored; no data loss occurs since emails remain in the inbox.
- **Excel schema changes**: The Excel processor MUST validate columns against the expected `documents` schema. Unknown columns are logged and ignored. Missing required columns cause the entire file to be rejected with a descriptive validation error. Column renames require a configuration update to the column mapping.
- **CMS API unavailability**: When the CMS API is unreachable during tag suggestion or article recommendation, the agent MUST return a user-friendly error message ("CMS is currently unavailable, please try again later") and log the failure with the HTTP status/timeout details. No fallback to cached data in MVP.
- **Concurrent ingestion for same date**: The upsert key (sheet_name, row_number) combined with database-level row locking ensures concurrent ingestion of the same date's data is safe. The last write wins. Celery task concurrency is limited to 1 for ingestion tasks to avoid unnecessary contention.
- **Invalid structured query parameters**: The analytics tool functions MUST validate all AnalyticsQuery fields via Pydantic before execution. Invalid metric names, unsupported aggregations, or out-of-range dates return a validation error to the agent, which reformulates or asks the user for clarification.
- **AI provider rate limiting**: The AI provider adapter MUST implement exponential backoff with jitter (max 3 retries, base 1s) on 429 responses. If retries are exhausted, the error propagates to the agent, which informs the user the system is temporarily busy.
- **Oversized documents**: Documents exceeding the LLM context window are handled by the chunking pipeline (RecursiveCharacterTextSplitter). For Q&A, only the top-K most relevant chunks (by vector similarity) are injected into the prompt, staying within the provider's context limit. No single-chunk assumption.

## Clarifications

### Session 2026-03-05

- Q: How should the analytics agent access data (NL-to-SQL vs alternatives)? → A: Hybrid approach — structured query objects + safe tool functions as foundation (C+B), augmented by RAG/vector retrieval for context (A) and pre-computed daily/weekly summaries for common queries (D). No raw SQL generation.
- Q: How should the assistant access articles for tags/recommendations? → A: CMS API for single-article fetch by ID; direct MongoDB queries for bulk similarity search across the article corpus.
- Q: What is the primary content language? → A: Primarily English with occasional Arabic. English-optimized embedding models (all-MiniLM-L6-v2) are sufficient; Arabic handling is best-effort.
- Q: What is the chat interface delivery mechanism? → A: API-only (FastAPI REST endpoints). No frontend in scope. WebSocket streaming deferred to a later phase.
- Q: How do company documents enter the system? → A: Both API upload endpoint (admin uploads files) and a watched folder that the system monitors for new files.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide REST API endpoints for conversational chat where clients can send natural-language questions and receive formatted responses. No frontend is in scope; WebSocket streaming is deferred.
- **FR-002**: System MUST interpret analytics questions using a hybrid approach: the agent generates structured query objects (not raw SQL) that pre-built tool functions execute safely, augmented by vector retrieval for context and pre-computed summaries for common queries.
- **FR-002a**: System MUST provide publishing time recommendations by analyzing historical engagement patterns across day-of-week and time-of-day dimensions.
- **FR-003**: System MUST monitor a configured Gmail inbox for incoming emails with Excel report attachments and automatically ingest valid reports into `documents`.
- **FR-004**: System MUST support manual triggering of Excel report ingestion in addition to automated monitoring.
- **FR-005**: System MUST fetch article content from external CMS APIs given an article ID and suggest relevant tags from the `tags` table.
- **FR-006**: System MUST fetch article content from external CMS APIs given an article ID and recommend related stories from the article database.
- **FR-007**: System MUST accept company documents (PDF, images, Excel, text files) via API upload endpoint and watched folder, process them into chunks with vector embeddings, and answer questions about their content using retrieval-augmented generation.
- **FR-008**: System MUST persist conversation history (messages, operations, metadata) in the `conversations` and `messages` tables.
- **FR-009**: System MUST support multiple AI providers through a pluggable provider interface, switchable via configuration.
- **FR-010**: System MUST implement a pluggable data adapter interface that allows adding new data sources without modifying existing agent or orchestration code.
- **FR-011**: System MUST validate all incoming Excel data against the expected schema before database insertion, rejecting invalid rows with logged errors.
- **FR-012**: System MUST perform idempotent data ingestion: re-processing the same report MUST NOT create duplicate records.
- **FR-013**: System MUST support user authentication with both local credentials and Active Directory integration.
- **FR-014**: System MUST use an agentic architecture where specialized agents collaborate through an orchestrator.
- **FR-015**: System MUST generate vector embeddings for tags to enable semantic tag matching.
- **FR-016**: System MUST validate all structured query objects before execution, ensuring only safe read operations are permitted through the tool function layer. Safe operations are limited to: SELECT queries with parameterized WHERE clauses, aggregate functions (COUNT, SUM, AVG, MAX, MIN), time-range filtering, and platform-specific filtering. Prohibited operations include: DDL statements, UPDATE/DELETE/INSERT, dynamic SQL construction, unlimited result sets (>10K rows), and cross-table JOINs beyond the documents table.

### Key Entities

- **Analytics Record**: A daily social media performance record with profile info, engagement metrics, reach metrics, impression metrics, and video metrics. Maps to `documents` columns.
- **Tag**: A content classification label with slug, name, description, variations (synonyms), primary flag, and embedding vector.
- **Article**: A content piece in the CMS with title, body, metadata, and associated tags. Single-article fetch via CMS API; bulk similarity search via direct MongoDB queries.
- **Document**: A company document (HR policy, procedure, guide) chunked and stored with vector embeddings for retrieval.
- **Conversation**: A chat session containing a sequence of user and assistant messages with operation metadata.
- **User**: An authenticated user with local or Active Directory credentials, activity tracking, and session management.
- **Data Adapter**: A pluggable component implementing a standardized interface for ingesting data from external sources.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can ask analytics questions in natural language and receive accurate answers within 10 seconds for queries spanning up to 1 year of daily data.
- **SC-002**: Excel report ingestion processes a typical report (up to 10,000 rows) within 2 minutes from email receipt to database availability.
- **SC-003**: Tag suggestions for an article return relevant tags with at least 80% user acceptance rate (users keep 4 out of 5 suggested tags on average). Acceptance rate is measured by tracking tag retention in the CMS: when users modify an article's suggested tags, the system logs which suggested tags were kept vs removed via a tag feedback API endpoint that the CMS calls after tag edits.
- **SC-004**: Related article recommendations return topically relevant stories, with at least 70% of suggestions rated as relevant by content editors.
- **SC-005**: Document Q&A returns accurate answers with source citations for questions covered by ingested documents, with at least 85% accuracy as judged by document owners.
- **SC-006**: System supports switching between AI providers without code changes, verified by running the same query through different providers and receiving comparable results.
- **SC-007**: Adding a new data source adapter requires implementing only the adapter interface without modifying any existing agent, orchestrator, or service code.
- **SC-008**: System maintains conversation context across a session, correctly referencing previous messages in follow-up questions.
- **SC-009**: The platform runs fully on local development infrastructure with no cloud service dependencies required for development and testing.
