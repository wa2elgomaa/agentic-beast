# Tasks: Agentic AI Assistant Platform

**Input**: Design documents from `/specs/001-agentic-ai-assistant/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec. Test tasks are omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `backend/src/app/`, `backend/tests/`
- Paths assume the project structure defined in plan.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependencies, and Docker environment

- [x] T001 Create project directory structure per plan.md with all `__init__.py` files under `backend/src/app/`
- [x] T002 Create `backend/pyproject.toml` with all dependencies: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, pydantic, pydantic-settings, celery, redis, pandas, openpyxl, sentence-transformers, httpx, motor, structlog, python-jose, passlib[bcrypt], google-api-python-client, google-auth-oauthlib, strands-agents, langchain-text-splitters, pypdf2, alembic, pgvector, prometheus-client, sentry-sdk[fastapi]
- [x] T003 [P] Create `backend/.env.example` with all required environment variables (DATABASE_URL, REDIS_URL, OPENAI_API_KEY, GMAIL_CREDENTIALS_PATH, CMS_API_BASE_URL, MONGODB_URI, JWT_SECRET_KEY, etc.)
- [x] T004 [P] Create `backend/docker-compose.yml` with PostgreSQL 15 (pgvector extension), Redis 7, MongoDB, Prometheus, Grafana, and application service definitions
- [x] T005 [P] Create `backend/Dockerfile` for the FastAPI application with multi-stage build

**Checkpoint**: Project structure created, dependencies defined, Docker environment ready

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can begin

- [x] T006 Implement Pydantic Settings configuration in `backend/src/app/config.py` with all environment variables, validation, and provider switching support
- [x] T007 Implement async SQLAlchemy session factory in `backend/src/app/db/session.py` with asyncpg engine, session maker, and dependency injection helper
- [x] T008 [P] Set up Alembic configuration in `backend/alembic/` with `alembic.ini`, async `env.py`, and initial migration from existing `db/init.sql` schema (documents, tags, users, conversations, messages, password_reset_tokens tables plus the new summaries table). Include PostgreSQL range partitioning on `documents` table by `report_date` column (monthly partitions) and auto-partition creation for new months
- [x] T009 [P] Implement structlog configuration in `backend/src/app/logging.py` with JSON output, correlation ID middleware, and request/response logging
- [x] T010 [P] Create SQLAlchemy models for all existing tables: `backend/src/app/models/document.py` (documents table), `backend/src/app/models/tag.py` (tags table), `backend/src/app/models/user.py` (users table), `backend/src/app/models/conversation.py` (conversations + messages tables), `backend/src/app/models/summary.py` (new summaries table)
- [x] T011 Implement FastAPI application factory in `backend/src/app/main.py` with CORS, router registration, structlog middleware, lifespan events for DB/Redis connections, and OpenAPI metadata
- [x] T012 [P] Implement Celery application configuration in `backend/src/app/tasks/celery_app.py` with Redis broker, result backend, task autodiscovery, and beat schedule for email monitoring
- [x] T013 [P] Implement embedding service in `backend/src/app/services/embedding_service.py` using sentence-transformers all-MiniLM-L6-v2 for local embedding generation with batch support
- [x] T014 [P] Implement `DataAdapter` abstract base class in `backend/src/app/adapters/base.py` with connect/disconnect/fetch_data/get_status methods and `AdapterStatus` model
- [x] T015 [P] Implement adapter registry in `backend/src/app/adapters/registry.py` with register/discover/get_adapter methods
- [x] T016 [P] Implement `AIProvider` abstract base class in `backend/src/app/providers/base.py` with complete/embed methods, `CompletionResponse` and `Message` models
- [x] T017 [P] Implement OpenAI provider in `backend/src/app/providers/openai_provider.py` implementing `AIProvider` with chat completion and embedding via OpenAI SDK
- [x] T018 [P] Implement Bedrock provider in `backend/src/app/providers/bedrock_provider.py` implementing `AIProvider` with chat completion via boto3 Bedrock runtime
- [x] T019 Implement AI provider factory in `backend/src/app/providers/__init__.py` that selects provider based on config (AI_PROVIDER env var)
- [x] T020 [P] Implement base agent interface in `backend/src/app/agents/base.py` with capability declaration, health status, Strands Agents SDK integration pattern, and Redis-based agent state management (store/retrieve agent execution state, session context, and health status via Redis using the configured Redis connection)
- [x] T021 Implement agent orchestrator in `backend/src/app/agents/v1/orchestrator_agent.py` with intent classification, agent routing, and Strands SDK agent coordination
- [x] T022 [P] Implement JWT authentication service in `backend/src/app/services/auth_service.py` with login (local bcrypt + AD LDAP bind), token generation, token validation
- [x] T023 [P] Implement auth API router in `backend/src/app/api/auth.py` with POST /auth/login endpoint and FastAPI dependency for JWT validation
- [x] T024 [P] Implement health check router in `backend/src/app/api/health.py` with GET /health endpoint checking PostgreSQL, Redis, Celery, and all agent statuses
- [x] T025 [P] Implement Pydantic request/response schemas for chat in `backend/src/app/schemas/chat.py` (ChatRequest, ChatResponse, ConversationListResponse, MessageListResponse)
- [x] T026 Implement chat service in `backend/src/app/services/chat_service.py` with conversation creation, message persistence, conversation history retrieval, and orchestrator invocation
- [x] T027 Implement chat API router in `backend/src/app/api/chat.py` with POST /chat, GET /conversations, GET /conversations/{id}/messages endpoints
- [x] T027a [P] Configure MongoDB connection in `backend/src/app/config.py` with MONGODB_URI setting and create MongoDB client factory in `backend/src/app/db/mongo_session.py` with motor async driver, database connection management
- [ ] T027b [P] Add Active Directory integration testing task in `backend/tests/integration/test_auth_ad.py` with LDAP bind verification, user attribute mapping validation, fallback to local auth testing

**Checkpoint**: Foundation ready — database connected, auth working, chat endpoint accepting messages and routing to orchestrator, all agent/adapter/provider interfaces defined

---

## Phase 3: User Story 1 — Analytics Data Querying (Priority: P1)

**Goal**: Users can ask natural-language analytics questions and receive accurate answers via the hybrid data access layer (structured queries + tool functions + RAG + summaries)

**Independent Test**: Send analytics questions via POST /chat and verify correct results against known data in `documents`

### Implementation for User Story 1

- [x] T028 [P] [US1] Implement structured query schemas in `backend/src/app/schemas/analytics.py` with AnalyticsQuery, DateRange, QueryResult Pydantic models supporting metric/aggregation/platform/date_range/group_by/order_by/limit fields
- [x] T029 [P] [US1] Implement analytics tool functions in `backend/src/app/tools/analytics_tools.py` with: `execute_query()` (aggregation queries), `get_publishing_insights()` (day-of-week/time analysis) — each accepting AnalyticsQuery and executing safe parameterized SQL via SQLAlchemy
- [x] T030 [P] [US1] Implement summary service in `backend/src/app/services/summary_service.py` with methods to compute daily/weekly/monthly aggregations, store in summaries table, and query pre-computed summaries for common metrics
- [x] T031 [US1] Implement analytics agent in `backend/src/app/agents/analytics_agent.py` using Strands Agents SDK pattern with: tool registration (analytics_tools), intent understanding for analytics questions, structured query generation from NL, result formatting, publishing time recommendations
- [x] T032 [US1] Register analytics agent with orchestrator — create `backend/src/app/agents/init.py` to initialize and register AnalyticsAgent, route analytics-related intents to AnalyticsAgent
- [ ] T032a [P] [US1] Create Google Cloud service account in Google Cloud Console with Gmail API access, generate service account key JSON file, document credential configuration steps in `backend/docs/gmail-setup.md` with environment variable mapping

**Checkpoint**: User Story 1 fully functional — analytics questions via /chat return correct results using hybrid approach

---

## Phase 4: User Story 2 — Gmail Excel Report Ingestion (Priority: P1)

**Goal**: System monitors Gmail inbox, downloads Excel attachments, validates data, and upserts into `documents` table with idempotent processing

**Independent Test**: Send a sample Excel report email to the monitored inbox, trigger ingestion via POST /ingest/trigger, and verify records in `documents`

### Implementation for User Story 2

- [x] T033 [P] [US2] Implement Gmail adapter in `backend/src/app/adapters/gmail_adapter.py` implementing `DataAdapter` with OAuth2 service account auth, inbox polling, attachment download, email label marking for processed emails
- [x] T034 [P] [US2] Implement Excel processor in `backend/src/app/processors/excel_processor.py` with: sheet reading via openpyxl, column mapping to `documents` schema, row-level Pydantic validation, error collection for invalid rows, batch output as list of validated dicts
- [x] T035 [P] [US2] Implement ingestion schemas in `backend/src/app/schemas/ingestion.py` with IngestTriggerResponse, IngestStatusResponse, IngestResult, RowError Pydantic models
- [x] T036 [US2] Implement ingestion service in `backend/src/app/services/ingestion_service.py` with: Gmail adapter invocation, Excel processor pipeline, bulk upsert into `documents` (ON CONFLICT sheet_name, row_number DO UPDATE), embedding generation for ingested rows, summary recomputation trigger, result tracking (inserted/updated/failed counts)
- [x] T037 [US2] Implement Celery email monitor task in `backend/src/app/tasks/email_monitor.py` as periodic task (configurable interval, default 5min) that invokes ingestion service
- [x] T038 [US2] Implement Celery Excel ingest task in `backend/src/app/tasks/excel_ingest.py` as async task for manual trigger that processes a specific email or file
- [x] T039 [US2] Implement Celery summary compute task in `backend/src/app/tasks/summary_compute.py` triggered after successful ingestion to recompute affected summaries
- [x] T040 [US2] Implement ingestion API router in `backend/src/app/api/ingestion.py` with POST /ingest/trigger and GET /ingest/status/{task_id} endpoints
- [x] T041 [US2] Implement data ingestion agent in `backend/src/app/agents/ingestion_agent.py` using Strands Agents SDK to handle chat-based ingestion queries (e.g., "ingest latest reports", "check ingestion status") and register with orchestrator
- [x] T042 [US2] Register Gmail adapter with adapter registry — update `backend/src/app/agents/init.py` to register GmailAdapter and IngestionAgent during initialization

**Checkpoint**: User Story 2 fully functional — Gmail emails with Excel attachments are automatically processed and data appears in `documents` table

---

## Phase 5: User Story 3 — Tag Suggestion for Articles (Priority: P2)

**Goal**: Users ask for tag suggestions for an article ID; system fetches article from CMS API, matches against tags table using semantic similarity, returns ranked tags

**Independent Test**: Send "Suggest 5 tags for article {id}" via /chat and verify relevant tags returned from `tags` table

### Implementation for User Story 3

- [x] T043a [P] [US3] Define CMS API contract in `backend/docs/cms-api-contract.md` specifying: article endpoint schema (GET /articles/{id}), authentication method (API key or OAuth), response format with required fields (id, title, body, metadata), error handling (404, 403, rate limits)
- [x] T043 [P] [US3] Implement CMS API client tools in `backend/src/app/tools/cms_tools.py` with: `fetch_article_by_id()` (single article via CMS REST API using httpx async), `search_articles()` (bulk search via direct MongoDB using motor), article content extraction and normalization
- [x] T044 [P] [US3] Implement tag matching tools in `backend/src/app/tools/tag_tools.py` with: `find_similar_tags()` (compute embedding of article content, vector similarity search against tags.embedding in PostgreSQL), `rank_tags_by_relevance()` (combine semantic similarity + keyword matching scores), return top N tags with confidence scores
- [x] T045 [US3] Implement tagging agent in `backend/src/app/agents/tagging_agent.py` using Strands Agents SDK with: CMS tools + tag tools registration, intent parsing for "suggest N tags for article X" pattern, article content fetching, tag ranking, formatted response with confidence scores
- [x] T046 [US3] Register tagging agent with orchestrator — update `backend/src/app/agents/v1/orchestrator_agent.py` to route tag-suggestion intents to TaggingAgent

**Checkpoint**: User Story 3 fully functional — tag suggestions via /chat return ranked tags from the tags table

---

## Phase 6: User Story 4 — Related Article Recommendation (Priority: P2)

**Goal**: Users ask for related articles to a given article ID; system fetches article from CMS, searches MongoDB for semantically similar articles, returns ranked recommendations

**Independent Test**: Send "Find 3 similar articles to {id}" via /chat and verify topically related articles returned

### Implementation for User Story 4

- [x] T047 [P] [US4] Extend CMS tools in `backend/src/app/tools/cms_tools.py` with: `find_similar_articles()` (generate embedding for target article, vector similarity search in MongoDB articles collection), `format_article_recommendation()` (extract title, ID, relevance explanation)
- [x] T048 [US4] Implement recommendation agent in `backend/src/app/agents/recommendation_agent.py` using Strands Agents SDK with: CMS tools registration, intent parsing for "suggest/find N related/similar articles/stories" pattern, article fetching, similarity search, formatted response with titles and relevance
- [x] T049 [US4] Register recommendation agent with orchestrator — update `backend/src/app/agents/v1/orchestrator_agent.py` to route article-recommendation intents to RecommendationAgent

**Checkpoint**: User Story 4 fully functional — article recommendations via /chat return related stories from MongoDB

---

## Phase 7: User Story 5 — Company Document Q&A (Priority: P3)

**Goal**: Admins upload company documents via API or watched folder; system chunks, embeds, and stores them; users ask questions and get RAG-powered answers with source citations

**Independent Test**: Upload a sample PDF via POST /documents/upload, then ask a question about its content via /chat

### Implementation for User Story 5

- [x] T050 [P] [US5] Implement document processor in `backend/src/app/processors/document_processor.py` with: PDF text extraction (PyPDF2), Excel content extraction (openpyxl), plain text reading, LangChain RecursiveCharacterTextSplitter for chunking with overlap, metadata preservation (filename, page number, chunk index)
- [x] T051 [P] [US5] Implement document upload schemas in `backend/src/app/schemas/documents.py` with DocumentUploadResponse, DocumentStatus Pydantic models
- [x] T052 [P] [US5] Implement document retrieval tools in `backend/src/app/tools/document_tools.py` with: `search_documents()` (embed query, vector similarity search in documents table where doc_metadata indicates company document), `format_citations()` (extract source document name, page, chunk)
- [x] T053 [US5] Implement Celery document ingest task in `backend/src/app/tasks/document_ingest.py` for processing uploaded files: chunk → embed → store in documents table with doc_metadata tagging source type as 'company_document'
- [x] T054 [US5] Implement Celery folder watch task in `backend/src/app/tasks/folder_watch.py` as periodic task that monitors `watched_documents/` directory for new files and triggers document_ingest for each
- [x] T055 [US5] Implement document upload API router in `backend/src/app/api/documents.py` with POST /documents/upload (multipart form) that queues document_ingest Celery task
- [x] T056 [US5] Implement document Q&A agent in `backend/src/app/agents/document_agent.py` using Strands Agents SDK with: document_tools registration, RAG retrieval pipeline (embed question → search relevant chunks → inject into LLM context → generate answer with citations)
- [x] T057 [US5] Register document agent with orchestrator — update `backend/src/app/agents/v1/orchestrator_agent.py` to route document-Q&A intents to DocumentAgent

**Checkpoint**: User Story 5 fully functional — documents uploaded and processed, Q&A returns accurate answers with source citations

---

## Phase 8: User Story 6 — General Smart Assistant (Priority: P3)

**Goal**: Out-of-scope questions are handled by a general-purpose LLM response without querying internal databases

**Independent Test**: Ask "What is the capital of France?" via /chat and verify correct general knowledge response

### Implementation for User Story 6

- [x] T058 [US6] Implement general assistant agent in `backend/src/app/agents/general_agent.py` using Strands Agents SDK as a fallback agent that passes the user message directly to the AI provider without any tool invocation, handling general knowledge and conversational responses
- [x] T059 [US6] Register general agent as the fallback in orchestrator — update `backend/src/app/agents/v1/orchestrator_agent.py` to route unclassified intents to GeneralAgent

**Checkpoint**: User Story 6 fully functional — general questions get helpful LLM responses

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T060 [P] Add error handling middleware in `backend/src/app/main.py` for consistent error response format (code, message, details) across all endpoints
- [x] T061 [P] Add rate limiting configuration for AI provider calls in `backend/src/app/providers/base.py` with configurable retry logic and exponential backoff
- [x] T062 [P] Create seed data script in `backend/scripts/seed_data.py` to populate tags table with CSV tags (with embeddings) and create a default admin user for development
- [x] T062a [P] Create tag embedding migration script in `backend/scripts/backfill_tag_embeddings.py` that iterates all existing tags in the `tags` table, generates embeddings for name+description+variations using embedding_service, and updates the `embedding` column. Must be idempotent (skip tags that already have embeddings)
- [x] T063 [P] Add OpenAPI documentation enhancements in `backend/src/app/main.py` — ensure all endpoints have descriptions, example requests/responses, and proper tags
- [x] T064 [P] Implement Prometheus metrics exposition in `backend/src/app/metrics.py` with: request count/duration histograms, agent execution metrics (count, duration, success/failure), ingestion pipeline metrics (rows processed/failed, duration), and `/metrics` endpoint for Prometheus scraping
- [x] T065 [P] Add Prometheus and Grafana services to `backend/docker-compose.yml` with pre-configured datasource and a basic dashboard JSON for agent and ingestion metrics
- [x] T066 [P] Integrate Sentry SDK in `backend/src/app/main.py` with DSN from config, environment tagging, structlog breadcrumb integration, and sample rate configuration
- [x] T067 Run quickstart.md validation — execute all 8 verification scenarios (V1-V8) against running Docker Compose environment

---

---

## Phase 10: Phase 2 Foundational — Blocking Prerequisites

**Purpose**: New DB schema, S3 client, settings service, and webhook security primitives that ALL Phase 2 user stories depend on

- [ ] T068 Create Alembic migration `backend/alembic/versions/002_phase2_tables.py` adding: `article_vectors` table (id, article_id VARCHAR, content TEXT, embedding vector(384), published_at, metadata JSONB), `app_settings` table (key VARCHAR PK, value TEXT, is_secret BOOL, updated_at), `webhook_events` table (id UUID PK, source VARCHAR, event_type VARCHAR, payload JSONB, hmac_verified BOOL, processed_at, created_at)
- [x] T069 [P] Add S3 client configuration in `backend/src/app/config/config.py`: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET, AWS_REGION, AWS_DEFAULT_REGION — add aioboto3 (async S3 client) to `backend/pyproject.toml`; do NOT add boto3 directly (it is a transitive dependency of aioboto3)
- [x] T070 [P] Implement app settings service in `backend/src/app/services/settings_service.py` with: `get_setting(key)`, `set_setting(key, value, is_secret)`, `get_all_settings()`, `get_effective_provider_config()` — reads from `app_settings` table, falls back to env vars, caches in Redis with 60s TTL. **Note**: This service is the authoritative config adapter layer — all agents and the orchestrator MUST call `settings_service.get_effective_provider_config()` for runtime provider config; they must NOT read `config.py` directly. This preserves constitution Principle III (provider switching via config only) while enabling DB-backed overrides.
- [x] T071 [P] Implement HMAC webhook security utility in `backend/src/app/utils/webhook_security.py` with `verify_hmac_signature(payload_bytes, signature_header, secret)` → bool using `hmac.compare_digest`; add WEBHOOK_SECRET to config
- [x] T072 [P] Add S3 upload service in `backend/src/app/services/s3_service.py` with async `upload_file(file_bytes, filename, content_type) → s3_url`, `delete_file(s3_key)`, `generate_presigned_url(s3_key, expiry_seconds)` using aioboto3

**Checkpoint**: DB tables created, S3 client ready, settings service working, HMAC utility in place — Phase 2 user stories can begin

---

## Phase 11: US7 — Webhook Ingestion Pipeline (Priority: P1)

**Goal**: External systems (CMS, CRM, etc.) push data changes via authenticated webhook; system routes by event type — article events trigger re-vectorization, generic events upsert into DB

**Independent Test**: POST to `/ingest/webhook` with valid HMAC signature and `{"event_type": "article.published", "article_id": "abc123"}` — verify article is fetched from CMS and upserted into `article_vectors`

### Implementation for User Story 7

- [ ] T073 [P] [US7] Add webhook ingestion schemas in `backend/src/app/schemas/ingestion.py`: `WebhookPayload` (source, event_type, data dict), `WebhookResult` (event_id, routed_to, status)
- [x] T074 [P] [US7] Implement Celery webhook article task in `backend/src/app/tasks/webhook_ingest.py`: `process_article_webhook_task(article_id)` — fetch article from CMS via `fetch_article_by_id()`, chunk content, embed (384-dim), upsert into `article_vectors` ON CONFLICT article_id DO UPDATE embedding + content + updated_at
- [x] T075 [P] [US7] Implement Celery webhook generic task in `backend/src/app/tasks/webhook_ingest.py`: `process_generic_webhook_task(source, event_type, data)` — upsert into `webhook_events` with processed_at timestamp
- [x] T076 [US7] Implement webhook receiver router in `backend/src/app/api/webhooks.py`: `POST /ingest/webhook` — verify HMAC using `verify_hmac_signature()`, log webhook event to `webhook_events` table, route to `process_article_webhook_task` for event_type in `{article.published, article.updated, article.deleted}`, else to `process_generic_webhook_task`, return 202 Accepted
- [x] T077 [US7] Register webhooks router in `backend/src/app/main.py`

**Checkpoint**: Webhook endpoint live — CMS can push article publish/update events and have them automatically re-vectorized

---

## Phase 12: US8 — Multi-Source Document Ingestion with S3 (Priority: P1)

**Goal**: Documents uploaded via API are stored in S3 (persistent) AND chunked + embedded into pgvector; folder watcher upgraded to use the same S3+vector pipeline

**Independent Test**: Upload a PDF via `POST /admin/datasets` — verify file appears in S3, chunks appear in `documents` table with `doc_type='company_document'`, and document Q&A agent can answer questions about it

### Implementation for User Story 8

- [ ] T078 [P] [US8] Extend document upload schemas in `backend/src/app/schemas/documents.py` with: `DatasetListResponse` (items: list of `DatasetItem(id: UUID, filename, s3_url, size_bytes, doc_type, status, created_at)`), `DatasetDeleteResponse`; `id` is the UUID primary key of the `documents` metadata row
- [x] T079 [P] [US8] Update Celery document ingest task in `backend/src/app/tasks/document_ingest.py` to: (1) upload raw file to S3 via `s3_service.upload_file()` and store `s3_url` in chunk metadata, (2) chunk + embed as before, (3) upsert into `documents` with `s3_url` in `doc_metadata`
- [x] T080 [US8] Update document upload API router in `backend/src/app/api/documents.py`: add `POST /admin/datasets` (same multipart upload but returns `DatasetListResponse` item), `GET /admin/datasets` (list all company_document rows with s3_url), `DELETE /admin/datasets/{doc_id: UUID}` (delete from S3 + delete all vector rows sharing that doc's `doc_metadata.s3_url`)
- [x] T081 [US8] Update folder watch task in `backend/src/app/tasks/folder_watch.py` to call the updated `document_ingest_task` so watched files also get S3-backed storage; after successful S3 upload + vectorization, move the local file to `watched_documents/processed/` (create dir if absent) to prevent re-processing on the next watcher run

**Checkpoint**: All document uploads (API + folder) are S3-backed; document Q&A has persistent file references

---

## Phase 13: US9 — Admin Settings Dashboard (Priority: P1)

**Goal**: Admins can view and update application settings (model providers, API keys, intervals) via the UI without touching `.env` files; the orchestrator reads provider config from the settings service at runtime

**Independent Test**: Change `ORCHESTRATOR_MODEL` to `gpt-4o` via `PUT /admin/settings`, send a chat message — verify orchestrator logs show the new model name

### Implementation for User Story 9

- [x] T082 [P] [US9] Add settings schemas in `backend/src/app/schemas/settings.py`: `SettingItem` (key, value, is_secret, updated_at), `SettingsUpdateRequest` (items: list of `{key, value}`), `SettingsResponse`
- [x] T083 [P] [US9] Implement settings API router in `backend/src/app/api/settings.py`: `GET /admin/settings` (return all settings, mask is_secret values, include `cache_ttl_seconds: 60` in response so callers know max staleness), `PUT /admin/settings` (batch upsert, invalidate Redis cache key immediately), protected by admin JWT role claim
- [x] T084 [US9] Update orchestrator agent in `backend/src/app/agents/v1/orchestrator_agent.py` to call `settings_service.get_effective_provider_config()` on each invocation so model provider + API key are read from DB/env at runtime (no restart required)
- [x] T085 [US9] Register settings router in `backend/src/app/main.py`; seed default settings rows in `backend/scripts/seed_data.py` for keys: `ORCHESTRATOR_MODEL`, `ANALYTICS_AGENT_MODEL`, `CHAT_AGENT_MODEL`, `TAGGING_AGENT_MODEL`, `RECOMMENDATION_AGENT_MODEL`, `DOCUMENT_AGENT_MODEL`, `SEARCH_AGENT_MODEL`, `OPENAI_API_KEY` (is_secret=true), `GMAIL_MONITOR_INTERVAL_SECONDS`
- [x] T086 [P] [US9] Implement Settings page in `frontend/app/admin/settings/page.tsx`: fetch `GET /admin/settings`, render key/value form with masked secret fields, submit via `PUT /admin/settings`, show save confirmation toast

**Checkpoint**: Admins can switch model providers via UI; changes take effect immediately without restart

---

## Phase 14: US10 — Admin Datasets Dashboard (Priority: P2)

**Goal**: Admins manage uploaded company documents — upload new files, browse existing with S3-backed status, delete — all via a dedicated `/admin/datasets` UI page

**Independent Test**: Upload a PDF in the Datasets UI — verify it appears in the file list with status, and deleting it removes both the S3 object and the vector rows

### Implementation for User Story 10

- [x] T087 [P] [US10] Implement Datasets page in `frontend/app/admin/datasets/page.tsx`: list/create/edit/delete datasets, drag-and-drop file upload per dataset, embed status polling, file table with embed status badges — implemented using `/admin/datasets` API (8 routes)

**Checkpoint**: Datasets dashboard functional — non-technical admins can manage the RAG document corpus without CLI access

---

## Phase 15: US11 — Admin Tags Management Dashboard (Priority: P2)

**Goal**: Admins manage the tag corpus via a dashboard: add/edit/delete individual tags, CSV bulk-upload new tags, and trigger re-embedding; tags table is the authoritative source for the tagging agent

**Independent Test**: Add a new tag via the Tags UI → verify it appears in `tags` table with a 384-dim embedding; delete a tag → verify it's removed; CSV bulk upload of 50 tags → all 50 inserted with embeddings

### Implementation for User Story 11

- [x] T088 [P] [US11] Add tags CRUD schemas in `backend/src/app/schemas/tags.py`: `TagCreateRequest` (name, slug, description, variations list, is_primary bool), `TagUpdateRequest` (same fields, all optional), `TagResponse` (id, name, slug, description, variations, is_primary, has_embedding bool), `TagBulkUploadResponse` (inserted, updated, failed, errors)
- [x] T089 [P] [US11] Implement tags API router in `backend/src/app/api/tags.py`: `GET /admin/tags` (paginated list, search by name), `POST /admin/tags` (create single tag + generate embedding via embedding_service), `PUT /admin/tags/{id}` (update + re-embed), `DELETE /admin/tags/{id}`, `POST /admin/tags/bulk-upload` (accept CSV file with columns name,slug,description,variations,is_primary — parse via csv.DictReader, validate, bulk insert, generate embeddings in batches of 50), `POST /admin/tags/reembed-all` (queue Celery task to regenerate all tag embeddings)
- [ ] T090 [US11] Implement Celery tag re-embed task in `backend/src/app/tasks/tag_embed.py`: `reembed_all_tags_task()` — iterate all tags in batches of 100, call embedding_service, update tags.embedding column, idempotent (can re-run safely)
- [x] T091 [US11] Register tags router in `backend/src/app/main.py`
- [x] T092 [P] [US11] Implement Tags page in `frontend/app/admin/tags/page.tsx`: data table with pagination + search, Add Tag modal (name, slug, description, variations textarea, primary toggle), Edit/Delete row actions, CSV/XLSX Upload button (file picker → `POST /admin/tags/bulk-upload`), Re-embed All button with per-row ⚡ embed for unembedded tags, progress polling

**Checkpoint**: Tags dashboard fully functional — admins control the entire tag corpus; tagging agent has up-to-date embeddings

---

## Phase 16: US12 — CMS Article Scraper & Vectorization (Priority: P1)

**Goal**: All existing CMS articles are bulk-scraped, chunked, embedded, and stored in `article_vectors`; this is the foundation for the enhanced recommendation agent

**Independent Test**: Run the scraper task against the configured CMS; verify `article_vectors` table is populated with rows having non-null 384-dim embeddings; run `SELECT COUNT(*) FROM article_vectors` and confirm count matches expected article count

### Implementation for User Story 12

- [x] T093 [P] [US12] Add article scraper config to `backend/src/app/config/config.py`: `CMS_SCRAPE_BATCH_SIZE` (default 50), `CMS_SCRAPE_CONCURRENCY` (default 5), `CMS_ARTICLES_ENDPOINT` (e.g. `/articles?page={page}&per_page={per_page}`)
- [ ] T094 [P] [US12] Implement CMS article scraper service in `backend/src/app/services/article_scraper.py`: async `scrape_all_articles()` — paginated fetch from CMS REST API (httpx, respect rate limits with asyncio.Semaphore), extract id + title + body + published_at + metadata, yield batches of `CMS_SCRAPE_BATCH_SIZE`
- [ ] T095 [US12] Implement Celery article scrape task in `backend/src/app/tasks/article_scrape.py`: `scrape_and_vectorize_articles_task()` — call `article_scraper.scrape_all_articles()`, for each batch: chunk content (RecursiveCharacterTextSplitter, chunk_size=512, overlap=64), embed batch via embedding_service, bulk upsert into `article_vectors` ON CONFLICT article_id DO UPDATE; apply exponential backoff on CMS 429/503 per batch (max 5 retries, base 2s, full jitter via `random.uniform(0, base * 2**attempt)`); failed batches accumulate in `errors` list — do NOT abort the full run; log progress every 500 articles; return `{total_scraped, total_vectorized, errors}`
- [x] T096 [P] [US12] Add scraper trigger endpoint in `backend/src/app/api/admin.py` (or new `backend/src/app/api/scraper.py`): `POST /admin/scraper/run` (queue `scrape_and_vectorize_articles_task`, return task_id), `GET /admin/scraper/status/{task_id}` (Celery result status)
- [x] T097 [US12] Register scraper router in `backend/src/app/main.py`

**Checkpoint**: All CMS articles are vectorized in `article_vectors` — recommendation agent can now run pgvector similarity instead of MongoDB

---

## Phase 17: US13 — CMS Article Webhook (Priority: P2)

**Goal**: When an article is published or updated in the CMS, the CMS calls our webhook; the article is immediately re-fetched and re-vectorized without manual scraper runs

**Independent Test**: POST `{"event_type": "article.updated", "article_id": "test123"}` with valid HMAC to `/ingest/webhook`; verify `article_vectors` row for `test123` has updated `embedding` and `updated_at`

### Implementation for User Story 13

- [x] T098 [US13] Extend `process_article_webhook_task` in `backend/src/app/tasks/webhook_ingest.py` to handle `article.deleted` event: soft-delete by setting `deleted_at` on `article_vectors` row; create new migration `backend/alembic/versions/003_article_vectors_soft_delete.py` adding `deleted_at TIMESTAMPTZ NULL` to `article_vectors` (do NOT amend migration 002 after it has run — that would corrupt Alembic revision history)
- [x] T099 [P] [US13] Add article webhook documentation in `backend/docs/cms-webhook-integration.md`: expected payload format, HMAC header name (`X-TNN-Signature`), supported event types, retry behaviour, example curl commands

**Checkpoint**: Webhook pipeline handles full article lifecycle: publish → vectorize, update → re-vectorize, delete → soft-delete

---

## Phase 18: US14 — Enhanced Article Recommendation via pgvector (Priority: P2)

**Goal**: Recommendation agent migrated from MongoDB cosine similarity to pgvector `article_vectors` table; users provide article ID, agent fetches article from CMS, embeds it, queries `article_vectors` by cosine distance, returns top-N recommendations

**Independent Test**: Ask "Suggest 5 related stories for article {known_id}" via `/chat` — verify recommendations come from `article_vectors` (check query logs) and are topically relevant

### Implementation for User Story 14

- [x] T100 [P] [US14] Add `search_article_vectors(embedding, top_k, exclude_ids)` function to `backend/src/app/tools/cms_tools.py` — pgvector cosine similarity query against `article_vectors` using `<=>` operator, returns list of `{article_id, title, similarity_score}`
- [x] T101 [US14] Update recommendation agent in `backend/src/app/agents/recommendation_agent.py` to use `search_article_vectors()` instead of MongoDB `find_similar_articles()`; preserve the user-facing conversation flow (ask for N, show results, offer "suggest more" follow-up)

**Checkpoint**: Recommendation agent uses pgvector — faster, more consistent similarity search; no cross-DB dependency

---

## Phase 19: US15 — Enhanced Tag Suggestion via Article ID + pgvector (Priority: P2)

**Goal**: Tagging flow upgraded — user provides article ID, agent fetches article from CMS, embeds its full content, queries `tags` via pgvector cosine similarity, returns top-N ranked tags with scores; supports "more tags" follow-up

**Independent Test**: Ask "Suggest 8 tags for article {known_id}" via `/chat` — verify tags are pulled from `tags.embedding` cosine search (not keyword only); ask "more tags" and verify different tags returned

### Implementation for User Story 15

- [x] T102 [P] [US15] Update `find_similar_tags()` in `backend/src/app/tools/tag_tools.py`: accept `article_embedding: list[float]` (pre-computed) AND `article_content: str` (compute on the fly if no embedding given); query `tags` by cosine similarity (`<=>`) with `exclude_ids` param for "more tags" flow; return top-K with `{tag_id, name, slug, similarity_score}`
- [x] T103 [US15] Update tagging agent in `backend/src/app/agents/tagging_agent.py`: (1) parse article ID from user message, (2) call `fetch_article_by_id()`, (3) embed article body via `embedding_service.embed_text()`, (4) call updated `find_similar_tags(article_embedding=...)`, (5) track already-shown tag IDs in conversation context for "more tags" follow-up handling

**Checkpoint**: Tag suggestion uses full article embedding — higher quality suggestions; repeat "more tags" returns fresh suggestions

---

## Phase 20: US16 — Google CSE Search Agent (Priority: P2)

**Goal**: A new Search Agent uses Google Custom Search API scoped to `thenationalnews.com`; users can search for articles, authors, or topics; activatable via the frontend tool selector

**Independent Test**: Ask "Search for articles about Formula 1 at TNN" via `/chat` with search tool selected — verify response contains real article titles from thenationalnews.com

### Implementation for User Story 16

- [x] T104 [P] [US16] Add Google CSE config to `backend/src/app/config/config.py`: `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_ID` (Custom Search Engine ID), `GOOGLE_CSE_SITE` (default `thenationalnews.com`), `GOOGLE_CSE_MAX_RESULTS` (default 10)
- [x] T105 [P] [US16] Implement `search_tnn` tool in `backend/src/app/tools/search_tools.py`: async function using httpx to call `https://www.googleapis.com/customsearch/v1?key={key}&cx={cx}&siteSearch={site}&q={query}&num={n}` — parse items list into `{title, link, snippet}` list; raise structured error on API quota/auth failure
- [x] T106 [US16] Implement search agent in `backend/src/app/agents/search_agent.py` using Strands Agents SDK: register `search_tnn` tool, system prompt instructs agent to format results as numbered list with title + link + excerpt, handle "no results" gracefully, support follow-up queries ("search for more")
- [x] T107 [US16] Register search agent with orchestrator in `backend/src/app/agents/v1/orchestrator_agent.py` as `search_tool` — add to tools list with description `"Search thenationalnews.com for articles, topics, or authors using Google Custom Search"`
- [x] T108 [P] [US16] Add GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID to settings seed in `backend/scripts/seed_data.py` (is_secret=true for API key)

**Checkpoint**: Search agent live — users can search TNN content directly from the chat interface

---

## Phase 21: US17 — Frontend Tool Selector (Priority: P2)

**Goal**: The `MessageInput` component gains a `+` icon button that opens a tool picker; selecting Search or Documents activates the corresponding agent for that turn via a `tool_hint` param in the chat request payload

**Independent Test**: Click `+` → select `Search` → type "Formula 1" → submit; verify the chat API request includes `{"tool_hint": "search"}` and response comes from Search agent

### Implementation for User Story 17

- [x] T109 [P] [US17] Extend `POST /chat` request schema in `backend/src/app/schemas/chat.py`: add optional `tool_hint: Literal["search", "documents", "analytics", "tags", "recommendation"] | None = None`; **Note**: `tool_hint` is only honoured on the REST POST `/chat` endpoint — the WebSocket voice path (`/ws/voice`) MUST ignore it (no schema change needed on WS side; orchestrator checks transport and skips hint when `source == "voice"`)
- [x] T110 [US17] Update chat service in `backend/src/app/services/chat_service.py` to pass `tool_hint` through to orchestrator; update orchestrator agent in `backend/src/app/agents/v1/orchestrator_agent.py` to bypass LLM routing when `tool_hint` is present and `source != "voice"` — direct dispatch to the specified agent; if `source == "voice"`, log a debug warning and fall back to normal LLM routing
- [x] T111 [P] [US17] Create `ToolSelector` component in `frontend/components/ToolSelector.tsx`: renders a `+` icon button, on click shows a popover/dropdown with tool options (icon + label + description): Search (`MagnifyingGlassIcon`, "Search thenationalnews.com"), Documents (`DocumentTextIcon`, "Ask about uploaded documents"); selected tool shows as a badge pill on the input; `onSelect(tool: string | null)` callback
- [x] T112 [US17] Integrate `ToolSelector` into `frontend/components/MessageInput.tsx`: add `ToolSelector` to the left of the send button, pass selected tool into the chat request payload as `tool_hint`, clear selection after message is sent
- [x] T113 [P] [US17] Add tool hint display in `frontend/components/` chat message list — show a small badge on assistant messages indicating which tool was used (e.g. "via Search", "via Documents")

**Checkpoint**: Tool selector functional — users can explicitly activate Search or Documents agent from the chat input

---

## Phase 22: Phase 2 Polish & Cross-Cutting

**Purpose**: Cross-cutting improvements for Phase 2 features

- [x] T114 [P] Add webhook event monitoring endpoint `GET /admin/webhooks/events` (paginated, filterable by source/event_type/date) in `backend/src/app/api/webhooks.py` for ops visibility
- [x] T115 [P] Update Prometheus metrics in `backend/src/app/metrics.py` for Phase 2: search_requests_total, article_vectors_count gauge, tag_vectors_count gauge, webhook_events_total counter (by source + event_type), settings_cache_hit_ratio gauge
- [x] T116 [P] Add CSE quota guard in `backend/src/app/tools/search_tools.py`: track daily request count in Redis (`cse:daily:{date}` key with TTL = end of day); raise `QuotaExceededError` when within 10% of `GOOGLE_CSE_DAILY_LIMIT` (configurable, default 100)
- [x] T117 [P] Update `backend/.env.example` with all Phase 2 variables: `AWS_S3_BUCKET`, `AWS_REGION`, `WEBHOOK_SECRET`, `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_ID`, `GOOGLE_CSE_SITE`, `GOOGLE_CSE_DAILY_LIMIT`
- [x] T118 Add Phase 2 quickstart validation script in `backend/scripts/validate_phase2.py` covering: settings endpoint, webhook HMAC, S3 upload round-trip, article_vectors row count, tags CRUD, search tool CSE call
- [x] T119 [P] [US11] Implement tag feedback endpoint `POST /api/tags/feedback` in `backend/src/app/api/tags.py` accepting `{article_id: str, suggested_tags: list[str], kept_tags: list[str]}` — persist each suggestion/kept pair to a new `tag_feedback` table (article_id, tag_slug, was_kept, recorded_at); add `tag_feedback` table to Alembic migration 002 or a new migration 004; this endpoint is called by the CMS after an editor saves their tag selections, enabling SC-003 acceptance rate measurement
- [x] T120 [P] Encrypt secret setting values before persisting to `app_settings` table: use Fernet symmetric encryption (`cryptography` library) with key from `SETTINGS_ENCRYPTION_KEY` environment variable; in `backend/src/app/services/settings_service.py` encrypt on `set_setting(is_secret=True)` and decrypt on `get_setting()` so callers always receive plaintext; add `cryptography` to `backend/pyproject.toml`; add `SETTINGS_ENCRYPTION_KEY` to `.env.example` with a note to generate via `Fernet.generate_key()` (OWASP A02 — protects API keys stored in DB)
- [x] T121 [P] [US9] Update frontend admin navigation in `frontend/app/admin/layout.tsx` (or equivalent sidebar component) to add links to `/admin/settings`, `/admin/datasets`, `/admin/tags` alongside any existing admin nav items; use icons consistent with the existing admin UI pattern (e.g., `Cog6ToothIcon` for Settings, `FolderIcon` for Datasets, `TagIcon` for Tags)
- [x] T122 [P] [US16] Create Google Custom Search Engine in Google Cloud Console scoped to `thenationalnews.com`: document all steps in `backend/docs/google-cse-setup.md` including CSE ID location, API key creation, site restriction configuration, and environment variable mapping (`GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_ID`)
- [x] T123 [P] Add LocalStack service to `docker-compose.yml` for local S3 emulation: add `localstack` service with `SERVICES=s3`, expose port 4566; update `backend/src/app/services/s3_service.py` to accept `AWS_ENDPOINT_URL` override (when set, routes all S3 calls to LocalStack instead of AWS); update `backend/.env.example` with `AWS_ENDPOINT_URL=http://localhost:4566` for local dev; this preserves SC-009 (no real cloud deps required for local development)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 Analytics (Phase 3)**: Depends on Foundational — no other story dependencies
- **US2 Ingestion (Phase 4)**: Depends on Foundational — no other story dependencies (but US1 benefits from data US2 produces)
- **US3 Tagging (Phase 5)**: Depends on Foundational — no other story dependencies
- **US4 Recommendation (Phase 6)**: Depends on Foundational + US3 (shares CMS tools) — can start after T043 from US3 is complete
- **US5 Document Q&A (Phase 7)**: Depends on Foundational — no other story dependencies
- **US6 General (Phase 8)**: Depends on Foundational — no other story dependencies
- **Polish (Phase 9)**: Depends on all user stories

### User Story Dependencies

- **US1 (Analytics)**: Independent after Foundational
- **US2 (Ingestion)**: Independent after Foundational (produces data for US1)
- **US3 (Tagging)**: Independent after Foundational
- **US4 (Recommendation)**: Shares CMS tools from US3 (T043); can start in parallel if T043 completed first
- **US5 (Document Q&A)**: Independent after Foundational
- **US6 (General)**: Independent after Foundational; simplest story

### Within Each User Story

- Models/schemas before tools
- Tools before agents
- Agents before orchestrator registration
- Tasks marked [P] can run in parallel within their phase

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- Foundational tasks T008-T010, T012-T018, T022-T025, T027a can all run in parallel
- Once Foundational completes: US1, US2, US3, US5, US6 can ALL start in parallel
- US4 can start after US3's T043a and T043 (CMS contract + tools) are complete
- US2 requires T032a (Google Cloud setup) before T033 (Gmail adapter implementation)

---

## Parallel Example: User Story 2

```bash
# Launch parallelizable US2 tasks together:
Task: "Implement Gmail adapter in backend/src/app/adapters/gmail_adapter.py"         # T033
Task: "Implement Excel processor in backend/src/app/processors/excel_processor.py"   # T034
Task: "Implement ingestion schemas in backend/src/app/schemas/ingestion.py"          # T035

# Then sequential tasks:
Task: "Implement ingestion service in backend/src/app/services/ingestion_service.py" # T036 (depends on T033, T034)
Task: "Implement email monitor task"                                                  # T037 (depends on T036)
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 4: User Story 2 (Ingestion — populates data)
4. Complete Phase 3: User Story 1 (Analytics — queries the data)
5. **STOP and VALIDATE**: Test full pipeline: email → ingestion → analytics query → answer
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US2 (Ingestion) → Data pipeline working → Demo
3. Add US1 (Analytics) → Core query capability → Demo (MVP!)
4. Add US3 (Tagging) → Content enrichment → Demo
5. Add US4 (Recommendation) → Content curation → Demo
6. Add US5 (Document Q&A) → Knowledge base → Demo
7. Add US6 (General) → Complete assistant → Demo
8. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 2 (Ingestion) → then US1 (Analytics)
   - Developer B: User Story 3 (Tagging) → then US4 (Recommendation)
   - Developer C: User Story 5 (Document Q&A) → then US6 (General)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- MVP = US2 (data) + US1 (queries) — recommend implementing in that order despite both being P1
