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

- [ ] T006 Implement Pydantic Settings configuration in `backend/src/app/config.py` with all environment variables, validation, and provider switching support
- [ ] T007 Implement async SQLAlchemy session factory in `backend/src/app/db/session.py` with asyncpg engine, session maker, and dependency injection helper
- [ ] T008 [P] Set up Alembic configuration in `backend/alembic/` with `alembic.ini`, async `env.py`, and initial migration from existing `db/init.sql` schema (documents, tags, users, conversations, messages, password_reset_tokens tables plus the new summaries table). Include PostgreSQL range partitioning on `documents` table by `report_date` column (monthly partitions) and auto-partition creation for new months
- [ ] T009 [P] Implement structlog configuration in `backend/src/app/logging.py` with JSON output, correlation ID middleware, and request/response logging
- [ ] T010 [P] Create SQLAlchemy models for all existing tables: `backend/src/app/models/document.py` (documents table), `backend/src/app/models/tag.py` (tags table), `backend/src/app/models/user.py` (users table), `backend/src/app/models/conversation.py` (conversations + messages tables), `backend/src/app/models/summary.py` (new summaries table)
- [ ] T011 Implement FastAPI application factory in `backend/src/app/main.py` with CORS, router registration, structlog middleware, lifespan events for DB/Redis connections, and OpenAPI metadata
- [ ] T012 [P] Implement Celery application configuration in `backend/src/app/tasks/celery_app.py` with Redis broker, result backend, task autodiscovery, and beat schedule for email monitoring
- [ ] T013 [P] Implement embedding service in `backend/src/app/services/embedding_service.py` using sentence-transformers all-MiniLM-L6-v2 for local embedding generation with batch support
- [ ] T014 [P] Implement `DataAdapter` abstract base class in `backend/src/app/adapters/base.py` with connect/disconnect/fetch_data/get_status methods and `AdapterStatus` model
- [ ] T015 [P] Implement adapter registry in `backend/src/app/adapters/registry.py` with register/discover/get_adapter methods
- [ ] T016 [P] Implement `AIProvider` abstract base class in `backend/src/app/providers/base.py` with complete/embed methods, `CompletionResponse` and `Message` models
- [ ] T017 [P] Implement OpenAI provider in `backend/src/app/providers/openai_provider.py` implementing `AIProvider` with chat completion and embedding via OpenAI SDK
- [ ] T018 [P] Implement Bedrock provider in `backend/src/app/providers/bedrock_provider.py` implementing `AIProvider` with chat completion via boto3 Bedrock runtime
- [ ] T019 Implement AI provider factory in `backend/src/app/providers/__init__.py` that selects provider based on config (AI_PROVIDER env var)
- [ ] T020 [P] Implement base agent interface in `backend/src/app/agents/base.py` with capability declaration, health status, Strands Agents SDK integration pattern, and Redis-based agent state management (store/retrieve agent execution state, session context, and health status via Redis using the configured Redis connection)
- [ ] T021 Implement agent orchestrator in `backend/src/app/agents/orchestrator.py` with intent classification, agent routing, and Strands SDK agent coordination
- [ ] T022 [P] Implement JWT authentication service in `backend/src/app/services/auth_service.py` with login (local bcrypt + AD LDAP bind), token generation, token validation
- [ ] T023 [P] Implement auth API router in `backend/src/app/api/auth.py` with POST /auth/login endpoint and FastAPI dependency for JWT validation
- [ ] T024 [P] Implement health check router in `backend/src/app/api/health.py` with GET /health endpoint checking PostgreSQL, Redis, Celery, and all agent statuses
- [ ] T025 [P] Implement Pydantic request/response schemas for chat in `backend/src/app/schemas/chat.py` (ChatRequest, ChatResponse, ConversationListResponse, MessageListResponse)
- [ ] T026 Implement chat service in `backend/src/app/services/chat_service.py` with conversation creation, message persistence, conversation history retrieval, and orchestrator invocation
- [ ] T027 Implement chat API router in `backend/src/app/api/chat.py` with POST /chat, GET /conversations, GET /conversations/{id}/messages endpoints
- [ ] T027a [P] Configure MongoDB connection in `backend/src/app/config.py` with MONGODB_URI setting and create MongoDB client factory in `backend/src/app/db/mongo_session.py` with motor async driver, database connection management
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

**Independent Test**: Send "Suggest 5 tags for article {id}" via /chat and verify relevant tags returned from `tags` table

### Implementation for User Story 3

- [ ] T043a [P] [US3] Define CMS API contract in `backend/docs/cms-api-contract.md` specifying: article endpoint schema (GET /articles/{id}), authentication method (API key or OAuth), response format with required fields (id, title, body, metadata), error handling (404, 403, rate limits)
- [ ] T043 [P] [US3] Implement CMS API client tools in `backend/src/app/tools/cms_tools.py` with: `fetch_article_by_id()` (single article via CMS REST API using httpx async), `search_articles()` (bulk search via direct MongoDB using motor), article content extraction and normalization
- [ ] T044 [P] [US3] Implement tag matching tools in `backend/src/app/tools/tag_tools.py` with: `find_similar_tags()` (compute embedding of article content, vector similarity search against tags.embedding in PostgreSQL), `rank_tags_by_relevance()` (combine semantic similarity + keyword matching scores), return top N tags with confidence scores
- [ ] T045 [US3] Implement tagging agent in `backend/src/app/agents/tagging_agent.py` using Strands Agents SDK with: CMS tools + tag tools registration, intent parsing for "suggest N tags for article X" pattern, article content fetching, tag ranking, formatted response with confidence scores
- [ ] T046 [US3] Register tagging agent with orchestrator — update `backend/src/app/agents/orchestrator.py` to route tag-suggestion intents to TaggingAgent

**Checkpoint**: User Story 3 fully functional — tag suggestions via /chat return ranked tags from the tags table

---

## Phase 6: User Story 4 — Related Article Recommendation (Priority: P2)

**Goal**: Users ask for related articles to a given article ID; system fetches article from CMS, searches MongoDB for semantically similar articles, returns ranked recommendations

**Independent Test**: Send "Find 3 similar articles to {id}" via /chat and verify topically related articles returned

### Implementation for User Story 4

- [ ] T047 [P] [US4] Extend CMS tools in `backend/src/app/tools/cms_tools.py` with: `find_similar_articles()` (generate embedding for target article, vector similarity search in MongoDB articles collection), `format_article_recommendation()` (extract title, ID, relevance explanation)
- [ ] T048 [US4] Implement recommendation agent in `backend/src/app/agents/recommendation_agent.py` using Strands Agents SDK with: CMS tools registration, intent parsing for "suggest/find N related/similar articles/stories" pattern, article fetching, similarity search, formatted response with titles and relevance
- [ ] T049 [US4] Register recommendation agent with orchestrator — update `backend/src/app/agents/orchestrator.py` to route article-recommendation intents to RecommendationAgent

**Checkpoint**: User Story 4 fully functional — article recommendations via /chat return related stories from MongoDB

---

## Phase 7: User Story 5 — Company Document Q&A (Priority: P3)

**Goal**: Admins upload company documents via API or watched folder; system chunks, embeds, and stores them; users ask questions and get RAG-powered answers with source citations

**Independent Test**: Upload a sample PDF via POST /documents/upload, then ask a question about its content via /chat

### Implementation for User Story 5

- [ ] T050 [P] [US5] Implement document processor in `backend/src/app/processors/document_processor.py` with: PDF text extraction (PyPDF2), Excel content extraction (openpyxl), plain text reading, LangChain RecursiveCharacterTextSplitter for chunking with overlap, metadata preservation (filename, page number, chunk index)
- [ ] T051 [P] [US5] Implement document upload schemas in `backend/src/app/schemas/documents.py` with DocumentUploadResponse, DocumentStatus Pydantic models
- [ ] T052 [P] [US5] Implement document retrieval tools in `backend/src/app/tools/document_tools.py` with: `search_documents()` (embed query, vector similarity search in documents table where doc_metadata indicates company document), `format_citations()` (extract source document name, page, chunk)
- [ ] T053 [US5] Implement Celery document ingest task in `backend/src/app/tasks/document_ingest.py` for processing uploaded files: chunk → embed → store in documents table with doc_metadata tagging source type as 'company_document'
- [ ] T054 [US5] Implement Celery folder watch task in `backend/src/app/tasks/folder_watch.py` as periodic task that monitors `watched_documents/` directory for new files and triggers document_ingest for each
- [ ] T055 [US5] Implement document upload API router in `backend/src/app/api/documents.py` with POST /documents/upload (multipart form) that queues document_ingest Celery task
- [ ] T056 [US5] Implement document Q&A agent in `backend/src/app/agents/document_agent.py` using Strands Agents SDK with: document_tools registration, RAG retrieval pipeline (embed question → search relevant chunks → inject into LLM context → generate answer with citations)
- [ ] T057 [US5] Register document agent with orchestrator — update `backend/src/app/agents/orchestrator.py` to route document-Q&A intents to DocumentAgent

**Checkpoint**: User Story 5 fully functional — documents uploaded and processed, Q&A returns accurate answers with source citations

---

## Phase 8: User Story 6 — General Smart Assistant (Priority: P3)

**Goal**: Out-of-scope questions are handled by a general-purpose LLM response without querying internal databases

**Independent Test**: Ask "What is the capital of France?" via /chat and verify correct general knowledge response

### Implementation for User Story 6

- [ ] T058 [US6] Implement general assistant agent in `backend/src/app/agents/general_agent.py` using Strands Agents SDK as a fallback agent that passes the user message directly to the AI provider without any tool invocation, handling general knowledge and conversational responses
- [ ] T059 [US6] Register general agent as the fallback in orchestrator — update `backend/src/app/agents/orchestrator.py` to route unclassified intents to GeneralAgent

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
