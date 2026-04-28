# Feature Specification: Agentic AI Assistant Platform

**Feature Branch**: `001-agentic-ai-assistant`
**Created**: 2026-03-05
**Status**: Partially Implemented — US1–US6 complete, US7–US17 specified and pending
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

A content editor asks the assistant to find related stories for a specific article. The assistant fetches the target article content via the CMS API, then performs bulk semantic similarity search against the pgvector `article_vectors` table (384-dim cosine distance) to find the top N most relevant related stories. The user can ask for more suggestions if the initial set is not suitable.

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

### User Story 7 - Webhook Ingestion from External Systems (Priority: P1)

An external system (e.g., the CMS publishing platform) sends a signed HTTP POST to the system whenever an article is published, updated, or deleted. The system verifies the HMAC signature, routes the event by type, and for article events immediately re-fetches the article from the CMS and re-vectorizes it so the recommendation and tagging agents always work against current content.

**Why this priority**: Webhooks are the real-time complement to the bulk scraper. Without them, vectors go stale as soon as articles are updated. This is P1 because it gates the quality of Phase 2 agent outputs.

**Independent Test**: POST `{"event_type": "article.published", "article_id": "test123"}` with valid HMAC to `POST /ingest/webhook` — verify `article_vectors` row for `test123` is created/updated within 5 seconds.

**Acceptance Scenarios**:

1. **Given** a valid HMAC-signed webhook payload for `article.published`, **When** it arrives at `/ingest/webhook`, **Then** the article is fetched from CMS and upserted into `article_vectors` and the endpoint returns 202 Accepted.
2. **Given** a webhook with an invalid or missing HMAC signature, **When** it arrives, **Then** the endpoint returns 401 and the event is logged but not processed.
3. **Given** an `article.updated` event, **When** processed, **Then** the existing `article_vectors` row is re-embedded with fresh content and `updated_at` is set.
4. **Given** an `article.deleted` event, **When** processed, **Then** the `article_vectors` row is soft-deleted (`deleted_at` set) so it no longer appears in similarity results.
5. **Given** an unrecognized event type, **When** processed, **Then** the payload is logged to `webhook_events` and a 202 is returned (graceful no-op).

---

### User Story 8 - Multi-Source Document Ingestion with S3 (Priority: P1)

An admin uploads company documents (PDF, Excel, plain text) via a dedicated datasets API endpoint. The file is stored in S3 for durability and simultaneously chunked, embedded, and stored in pgvector so the Document Q&A agent can answer questions about it immediately. The folder watcher is upgraded to use the same S3+pgvector pipeline.

**Why this priority**: The existing document pipeline lacked durable storage — files were only in the watched folder. S3 backing is required for production reliability and is a prerequisite for the Datasets Dashboard.

**Independent Test**: Upload a PDF via `POST /admin/datasets` — verify the file is accessible in S3, its chunks appear in the `documents` table with `doc_type='company_document'`, and asking a question about its content returns an accurate answer.

**Acceptance Scenarios**:

1. **Given** an admin uploads a PDF via `POST /admin/datasets`, **When** processing completes, **Then** the file exists in S3, chunks exist in `documents`, and `GET /admin/datasets` lists the file with status `completed`.
2. **Given** a file is deleted via `DELETE /admin/datasets/{id}`, **When** confirmed, **Then** the S3 object is deleted and all associated vector rows are removed from `documents`.
3. **Given** a file is placed in `watched_documents/`, **When** the folder watcher runs, **Then** the file is uploaded to S3 and vectorized identically to the API upload path.
4. **Given** an unsupported file type is uploaded, **When** the API receives it, **Then** it returns a 422 with a descriptive error; no S3 upload occurs.

---

### User Story 9 - Admin Settings Dashboard (Priority: P1)

An admin opens the Settings page in the admin board and sees all configurable application parameters (model providers, API keys, polling intervals) prefilled from the current configuration. They can update any value — including switching the model provider per agent — and save. The change takes effect within 60 seconds without a server restart. Secret values (API keys) are masked in the UI.

**Why this priority**: Without DB-backed settings, every environment change requires a `.env` file edit and container restart, blocking operational agility. This is foundational for Phase 2 operations.

**Independent Test**: Change `ORCHESTRATOR_MODEL` to `gpt-4o` via `PUT /admin/settings` — send a chat message and verify logs show the new model name within 60 seconds.

**Acceptance Scenarios**:

1. **Given** the settings page is loaded, **When** it renders, **Then** all settings from `app_settings` table are displayed; secret fields show masked values (e.g., `***`).
2. **Given** an admin updates `CHAT_AGENT_MODEL` and saves, **When** the next chat request arrives, **Then** the chat agent uses the new model (within the 60s cache TTL).
3. **Given** an admin sets an invalid value for a known numeric setting (e.g., `GMAIL_MONITOR_INTERVAL_SECONDS = "abc"`), **When** saved, **Then** a validation error is returned; the previous value is preserved.
4. **Given** a non-admin user attempts to call `PUT /admin/settings`, **When** the request is made, **Then** it returns 403 Forbidden.

---

### User Story 10 - Admin Datasets Dashboard (Priority: P2)

An admin opens the Datasets page and sees all ingested company documents with their filename, size, type, and processing status. They can upload new files (drag-and-drop), monitor processing progress, and delete documents they no longer want available to the chatbot.

**Why this priority**: Provides non-technical admins visibility and control over the RAG corpus without CLI access. Depends on US8 (S3 pipeline) being in place.

**Independent Test**: Upload a file in the Datasets UI — verify the file appears in the list with `processing` → `completed` status transition; delete it and verify it disappears.

**Acceptance Scenarios**:

1. **Given** the Datasets page loads, **When** rendered, **Then** all existing datasets are listed with filename, size in human-readable format, doc_type, and status.
2. **Given** an admin drops a PDF onto the upload zone, **When** upload starts, **Then** the file row immediately appears with status `processing` and transitions to `completed` once the Celery task finishes.
3. **Given** an admin clicks Delete on a dataset row, **When** confirmed in a dialog, **Then** the row disappears and subsequent document Q&A no longer returns content from that document.

---

### User Story 11 - Admin Tags Management Dashboard (Priority: P2)

A content admin opens the Tags page and sees a paginated, searchable table of all tags. They can add individual tags (name, slug, description, synonyms, primary flag), edit existing ones, delete tags, and bulk-import new tags by uploading a CSV file. When new tags are added, embeddings are generated automatically. Admins can also trigger a full re-embed of all tags when the embedding model changes.

**Why this priority**: Tag quality directly determines tagging agent accuracy. Admins need CRUD access to maintain and grow the tag corpus. Also provides the tag feedback mechanism for SC-003 measurement.

**Independent Test**: Add a new tag "Formula 1 Racing" via the Tags UI — verify it appears in `tags` table with a non-null 384-dim embedding; then bulk-upload a CSV of 5 tags — verify all 5 are inserted with embeddings.

**Acceptance Scenarios**:

1. **Given** the Tags page loads, **When** rendered, **Then** tags are displayed in a paginated table with search by name; embedding status is shown per row.
2. **Given** an admin adds a new tag with name, slug, description, and variations, **When** saved, **Then** the tag appears in the table and has a 384-dim embedding generated automatically.
3. **Given** an admin uploads a valid CSV (`name,slug,description,variations,is_primary`), **When** processed, **Then** all valid rows are inserted/updated, a summary shows `{inserted, updated, failed}`, and all new tags have embeddings.
4. **Given** an admin clicks "Re-embed All", **When** confirmed, **Then** a Celery task runs in the background and all tags receive fresh embeddings; progress is visible via a status indicator.
5. **Given** an admin deletes a tag, **When** confirmed, **Then** the tag is removed from the table and from pgvector; it no longer appears in tag suggestions.

---

### User Story 12 - CMS Article Scraper & Vectorization (Priority: P1)

A developer triggers a one-time bulk scrape of all existing CMS articles. The scraper paginates through the CMS REST API, chunks each article body, generates embeddings, and upserts all records into the `article_vectors` pgvector table. This is the initial corpus load that enables the pgvector-based recommendation and tagging agents.

**Why this priority**: The pgvector recommendation agent (US14) and the webhook freshness pipeline (US13) both depend on an initial corpus being loaded. Without it, article similarity returns empty results.

**Independent Test**: Trigger `POST /admin/scraper/run` — verify `article_vectors` row count grows and each row has a non-null 384-dim embedding; query against a known article ID and confirm its content is present.

**Acceptance Scenarios**:

1. **Given** the CMS contains N articles, **When** the scraper task completes, **Then** `article_vectors` contains at least N rows with non-null embeddings.
2. **Given** the scraper is run a second time (idempotent re-run), **When** it completes, **Then** existing rows are updated (not duplicated); row count does not exceed N.
3. **Given** the CMS API returns a 429 rate-limit during scraping, **When** encountered, **Then** the scraper applies exponential backoff (max 5 retries, base 2s) per batch and resumes; it does not abort the entire run.
4. **Given** `GET /admin/scraper/status/{task_id}` is polled during processing, **When** queried, **Then** it returns `{status, articles_scraped, articles_vectorized, errors}` reflecting real-time progress.

---

### User Story 13 - CMS Article Webhook Lifecycle (Priority: P2)

The CMS is configured to send HMAC-signed webhook events for every article lifecycle event (published, updated, deleted). The system handles each: published/updated articles are re-fetched and re-vectorized; deleted articles are soft-deleted in `article_vectors` so they no longer appear in recommendations.

**Why this priority**: Complements US12 (initial corpus) and US7 (webhook infrastructure). Together they ensure recommendations are based on current articles, not stale snapshots.

**Independent Test**: Publish an article in the CMS — within 10 seconds verify its `article_vectors` row exists; update it — verify `updated_at` changes; delete it — verify `deleted_at` is set and it no longer appears in similarity results.

**Acceptance Scenarios**:

1. **Given** an `article.published` webhook arrives, **When** processed, **Then** the article is fetched from CMS, chunked, embedded, and upserted into `article_vectors`.
2. **Given** an `article.updated` webhook arrives, **When** processed, **Then** the existing `article_vectors` row is re-embedded with current content and `updated_at` is refreshed.
3. **Given** an `article.deleted` webhook arrives, **When** processed, **Then** the `article_vectors` row gets `deleted_at` set and is excluded from all future similarity searches.

---

### User Story 14 - Enhanced Article Recommendation via pgvector (Priority: P2)

A content editor provides an article ID in chat. The recommendation agent fetches the article from the CMS, embeds its full content, queries `article_vectors` by cosine distance, and returns the top-N most similar articles with titles and relevance explanations. The user can ask for more if the initial suggestions are not suitable; previously shown article IDs are excluded from subsequent calls.

**Why this priority**: Migrates the recommendation agent from MongoDB ad-hoc similarity to the dedicated pgvector corpus (US12), yielding consistent, fast similarity search.

**Independent Test**: Ask "Suggest 5 related stories for article {known_id}" via `/chat` — verify the 5 returned article IDs exist in `article_vectors` and are topically related; ask "suggest more" and verify 5 different articles are returned.

**Acceptance Scenarios**:

1. **Given** `article_vectors` is populated, **When** the user asks "Recommend 5 stories similar to article abc123", **Then** the agent embeds abc123's content, queries pgvector, and returns 5 results with title and a one-sentence relevance note.
2. **Given** the user asks "Show me more", **When** the agent processes the follow-up, **Then** the previously returned article IDs are excluded and 5 new results are returned.
3. **Given** the target article has no close matches (similarity score below 0.4), **When** results are returned, **Then** the agent notes limited similarity alongside the best available results.

---

### User Story 15 - Enhanced Tag Suggestion via Article ID (Priority: P2)

A content editor provides an article ID in chat. The tagging agent fetches the full article from the CMS, embeds its content, queries the `tags` pgvector column by cosine distance, and returns the top-N most relevant tags with confidence scores. The user can ask for more if the initial set is not suitable; previously shown tag IDs are excluded from subsequent calls.

**Why this priority**: Upgrades the existing tagging agent (US3) from keyword-only matching to full-article embedding for higher quality suggestions, and adds the "more tags" conversational flow.

**Independent Test**: Ask "Suggest 8 tags for article {known_id}" via `/chat` — verify tags are retrieved using the article's full-text embedding (not keyword only); ask "more tags" and verify 8 different tags are returned.

**Acceptance Scenarios**:

1. **Given** the user asks "Suggest 8 tags for article xyz", **When** processed, **Then** the agent fetches the article, embeds it, queries `tags.embedding` by cosine similarity, and returns 8 tags with confidence scores.
2. **Given** the user asks "more tags", **When** the agent processes the follow-up, **Then** it excludes already-shown tag IDs and returns N fresh suggestions.
3. **Given** an invalid article ID is provided, **When** the CMS returns 404, **Then** the agent responds: "Article {id} was not found in the CMS."

---

### User Story 16 - Google Custom Search Agent (Priority: P2)

A user selects the "Search" tool from the chat input tool selector and types a query. The search agent calls the Google Custom Search API scoped exclusively to `thenationalnews.com` and returns a numbered list of matching articles with title, URL, and excerpt. The user can follow up with "search for more" to load the next page of results.

**Why this priority**: Provides real-time article discovery without relying on the vectorized article corpus, which may not yet include breaking news. Addresses the need to search by author, topic, or keyword across the live site.

**Independent Test**: With "Search" tool active, ask "Find articles about Formula 1" — verify the response contains real article titles and URLs from thenationalnews.com matching the query.

**Acceptance Scenarios**:

1. **Given** the user has selected the Search tool and submits a query, **When** the agent calls Google CSE, **Then** it returns up to 10 results formatted as a numbered list with title, URL, and excerpt.
2. **Given** the Google CSE API quota is exhausted for the day, **When** a search is attempted, **Then** the agent returns: "Search is currently unavailable (daily quota reached). Please try again tomorrow."
3. **Given** the user asks "search for more", **When** processed, **Then** results from the next page of the CSE response are returned, not a repeat of the first page.
4. **Given** a search returns no results, **When** rendered, **Then** the agent suggests alternative search terms.

---

### User Story 17 - Frontend Chat Tool Selector (Priority: P2)

A user sees a `+` icon button to the left of the chat input. Clicking it opens a popover listing available tools (Search, Documents). Selecting a tool attaches a badge pill to the input showing the active tool. When the message is submitted, the `tool_hint` is sent in the chat request, bypassing orchestrator LLM routing and dispatching directly to the specified agent. The selection clears after each message.

**Why this priority**: Tool selection gives power users explicit control over which agent handles their query, improving reliability and predictability compared to relying solely on the orchestrator's intent classification.

**Independent Test**: Click `+` → select "Search" → type "Formula 1" → submit — verify the chat request contains `{"tool_hint": "search"}` and the response comes from the search agent (not the chat agent); verify the badge disappears after send.

**Acceptance Scenarios**:

1. **Given** the user clicks `+`, **When** the popover opens, **Then** available tools are listed with an icon, label, and one-line description.
2. **Given** the user selects "Documents", **When** a message is typed and submitted, **Then** the request payload includes `tool_hint: "documents"` and the Document Q&A agent handles it.
3. **Given** a tool badge is active and the user sends a message, **When** sent, **Then** the badge is cleared and the next message has no tool hint (orchestrator routing resumes).
4. **Given** no tool is selected, **When** a message is submitted, **Then** no `tool_hint` is sent and the orchestrator routes normally.
5. **Given** the WebSocket voice path is active, **When** the user tries to select a tool, **Then** the tool selector is disabled with a tooltip "Tool selection not available in voice mode."

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

### Session 2026-04-28 (Phase 2 clarifications)

- Q: What is the expected data scale for Phase 2? → A: **Large scale** — >500K articles, >10M analytics records, >50K company documents. Design impact: `article_vectors` uses an **HNSW** pgvector index (not IVFFlat); Celery worker concurrency set to 16–32; S3 lifecycle policy recommended for documents older than 180 days.
- Q: What webhook delivery guarantee does the CMS provide, and how should duplicates be handled? → A: **At-least-once delivery with replay protection**. Each webhook payload includes a unique `event_id`; the `webhook_events` table records `(event_id, processed_at)` and the handler checks for existence before processing. Re-vectorization is idempotent (ON CONFLICT DO UPDATE), so replays are safe but should be skipped for performance.
- Q: How do users authenticate to the admin board (Settings, Datasets, Tags)? → A: **Existing JWT with `role` claim** — same `/auth/login` endpoint; `users.role` field values are `admin` / `user`; all `PUT /admin/*` and destructive `DELETE /admin/*` endpoints require `role == "admin"` in the JWT; the Next.js frontend reads the role from the decoded token and redirects non-admins to `/login`.
- Q: What is the Google CSE quota policy? → A: **Free tier only** — 100 queries/day hard limit. When the Google API returns 429 (quota exhausted), the search agent returns: "Search is currently unavailable (daily quota reached). Please try again tomorrow." No paid tier is provisioned; there is no configurable cap — quota management is Google-side only.
- Q: How does the CMS authenticate when calling `POST /api/tags/feedback` (SC-003)? → A: **HMAC-signed CMS callback** — same `X-TNN-Signature` header and `verify_hmac_signature()` as the webhook ingestion endpoint. No separate API key or user JWT is needed. The shared HMAC secret is stored as `WEBHOOK_HMAC_SECRET` in `app_settings` (is_secret=true).

### Session 2026-03-05

- Q: How should the analytics agent access data (NL-to-SQL vs alternatives)? → A: Hybrid approach — structured query objects + safe tool functions as foundation (C+B), augmented by RAG/vector retrieval for context (A) and pre-computed daily/weekly summaries for common queries (D). No raw SQL generation.
- Q: How should the assistant access articles for tags/recommendations? → A: CMS API for single-article fetch by ID; pgvector `article_vectors` table (cosine distance via `<=>` operator) for bulk similarity search across the article corpus. Initial corpus is populated by a bulk scraper task; kept fresh by CMS webhook re-vectorization.
- Q: What is the primary content language? → A: Primarily English with occasional Arabic. English-optimized embedding models (all-MiniLM-L6-v2) are sufficient; Arabic handling is best-effort.
- Q: What is the chat interface delivery mechanism? → A: API-only (FastAPI REST endpoints). No frontend in scope. WebSocket streaming deferred to a later phase.
- Q: How do company documents enter the system? → A: Both API upload endpoint (admin uploads files) and a watched folder that the system monitors for new files.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide REST API endpoints for conversational chat where clients can send natural-language questions and receive formatted responses. A Next.js admin board frontend is in scope for Phase 2 (Settings, Datasets, Tags dashboards). WebSocket voice streaming is a separate deferred capability.
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
- **FR-017**: System MUST use an HNSW index on `article_vectors.embedding` (pgvector `vector_cosine_ops`) to support large-scale similarity search (>500K articles) with sub-second query latency.
- **FR-018**: System MUST verify a unique `event_id` on each incoming webhook payload and skip re-processing if the `event_id` already exists in `webhook_events`, providing at-least-once delivery with replay protection.
- **FR-019**: All `/admin/*` write endpoints (PUT, DELETE) MUST require a JWT with `role == "admin"`; non-admin requests MUST return 403. The Next.js admin frontend MUST redirect to `/login` when the decoded role is not `admin`.
- **FR-020**: The Google Custom Search integration MUST operate within the free-tier limit (100 queries/day). When the Google CSE API returns a 429 response, the search agent MUST return the message "Search is currently unavailable (daily quota reached). Please try again tomorrow." No retry is attempted on quota exhaustion.
- **FR-021**: The `POST /api/tags/feedback` endpoint (SC-003 measurement) MUST authenticate callers using the same HMAC `X-TNN-Signature` verification as the webhook ingestion endpoint. Unauthenticated requests MUST return 401.
- **FR-016**: System MUST validate all structured query objects before execution, ensuring only safe read operations are permitted through the tool function layer. Safe operations are limited to: SELECT queries with parameterized WHERE clauses, aggregate functions (COUNT, SUM, AVG, MAX, MIN), time-range filtering, and platform-specific filtering. Prohibited operations include: DDL statements, UPDATE/DELETE/INSERT, dynamic SQL construction, unlimited result sets (>10K rows), and cross-table JOINs beyond the documents table.

### Key Entities

- **Analytics Record**: A daily social media performance record with profile info, engagement metrics, reach metrics, impression metrics, and video metrics. Maps to `documents` columns.
- **Tag**: A content classification label with slug, name, description, variations (synonyms), primary flag, and embedding vector.
- **Article**: A content piece in the CMS with title, body, metadata, and associated tags. Single-article fetch via CMS API; bulk similarity search via pgvector `article_vectors` cosine similarity (populated by bulk scraper, refreshed by webhook).
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
