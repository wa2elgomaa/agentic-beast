# Implementation Plan: Agentic AI Assistant Platform

**Branch**: `001-agentic-ai-assistant` | **Date**: 2026-03-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-agentic-ai-assistant/spec.md`

## Summary

Build a multi-agent AI assistant platform with pluggable data adapters, prioritizing Gmail Excel report ingestion and analytics querying. The system uses AWS Strands Agents SDK for agentic orchestration, a hybrid data access layer (structured query objects + tool functions + RAG + pre-computed summaries), and supports multiple AI providers (OpenAI + AWS Bedrock). REST API + Admin React frontend for ingestion management.

**Status as of 2026-04-28**: US1–6 (Analytics + Ingestion + Tag Suggestion + Recommendation + Document Q&A + General Agent) fully implemented and tested. Phase 2 specified: US7–17 cover Webhook ingestion, S3/multi-source document pipeline, Admin Settings/Datasets/Tags dashboards, CMS article vectorization, pgvector-enhanced agents, Google CSE search agent, and frontend tool selector. Next.js admin frontend added as Phase 2 scope.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, Strands Agents SDK, LangChain, Pydantic V2, SQLAlchemy (async), Celery, Redis, Pandas, Openpyxl
**Storage**: PostgreSQL 15+ (pgvector, table partitioning), MongoDB (articles via CMS/direct), Redis (agent state/cache), S3 (document storage — Phase 2)
**Testing**: pytest, pytest-asyncio, pytest-httpx (for CMS API mocking)
**Target Platform**: Linux server (Docker Compose for local dev, AWS for production)
**Project Type**: full-stack web application (FastAPI backend + Next.js frontend admin board — frontend added in Phase 2)
**Performance Goals**: Analytics queries <10s for 1 year of daily data; Excel ingestion <2min for 10k rows
**Constraints**: local-first development, async-first I/O, idempotent data ingestion (frontend admin board added in Phase 2; Phase 1 was API-only)
**Scale/Scope**: Single-team internal tool, ~10 concurrent users, ~365k analytics records/year, ~1000 articles in MongoDB

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Pluggable Adapter Architecture | PASS | `DataAdapter` base class in `backend/src/app/adapters/`; Gmail adapter is first implementation; adapter registry for discovery |
| II. Agent Autonomy with Orchestration | PASS | Each agent (Analytics, DataIngestion, Tagging, Recommendation, Document) independently testable; orchestrator routes via Strands SDK |
| III. Multi-Provider AI Abstraction | PASS | Provider factory in `backend/src/app/providers/`; OpenAI + Bedrock adapters; config-only switching |
| IV. Async-First Processing | PASS | FastAPI async endpoints; asyncpg for PostgreSQL; Celery for long-running ingestion tasks |
| V. Structured Observability | PASS | structlog with correlation IDs; agent execution logging; health check endpoints |
| VI. Data Integrity and Schema Validation | PASS | Pydantic V2 strict mode; Alembic migrations; idempotent upsert on (sheet_name, row_number) |
| VII. Incremental Delivery | PASS | Gmail adapter + Excel processor = MVP (US1+US2); each agent independently deployable |

No violations. All gates pass.

### Phase 2 Constitution Re-check *(2026-04-28)*

*Re-gate triggered by: S3 cloud dependency, Next.js frontend scope, Fernet secret encryption, webhook HMAC security, pgvector article corpus*

| Principle | Status | Phase 2 Evidence |
|-----------|--------|-----------------|
| I. Pluggable Adapter Architecture | PASS | Webhook ingestion added as new adapter path; folder-watch and API upload converge on the same `document_ingest_task` pipeline |
| II. Agent Autonomy with Orchestration | PASS | Search, Recommendation (pgvector), Tag agents added; each independently testable; orchestrator dispatches via `tool_hint` or LLM routing |
| III. Multi-Provider AI Abstraction | PASS | `settings_service` makes provider switchable at runtime from the Admin Settings UI without code changes |
| IV. Async-First Processing | PASS | Article scraper uses `asyncio.Semaphore` + httpx; webhook handler is async; all admin API endpoints are async |
| V. Structured Observability | PASS | Scraper logs progress every 500 articles; webhook events logged to `webhook_events`; settings cache-miss events are logged |
| VI. Data Integrity and Schema Validation | PASS | HMAC signature verified before webhook processing; Fernet encryption for secrets (`is_secret=true` rows in `app_settings`); all Phase 2 Pydantic schemas in strict mode |
| VII. Incremental Delivery | PASS | Phase 2 features are independently deployable: S3 (T069–T073), Admin Settings (T082–T086), Article Scraper (T093–T097), Tool Selector (T109–T113) |
| **NEW — SC-009 Local-First Dev** | PASS | LocalStack replaces real S3 in local dev (`AWS_ENDPOINT_URL` override in `s3_service`, T123); no cloud account required for development |
| **NEW — OWASP A02 Cryptographic Failures** | PASS | Admin setting secrets Fernet-encrypted at rest (T120); secret values masked in `GET /admin/settings` response and not returned in plaintext |

No Phase 2 constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-agentic-ai-assistant/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API contracts)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
backend/
├── src/
│   └── app/
│       ├── __init__.py
│       ├── main.py                  # FastAPI application factory
│       ├── config.py                # Pydantic Settings configuration
│       ├── agents/                  # Strands agent implementations
│       │   ├── __init__.py
│       │   ├── base.py              # Base agent interface
│       │   ├── orchestrator.py      # Agent orchestrator/router
│       │   ├── analytics_agent.py   # Analytics querying agent
│       │   ├── ingestion_agent.py   # Data ingestion agent
│       │   ├── tagging_agent.py     # Tag suggestion agent
│       │   ├── recommendation_agent.py  # Article recommendation agent
│       │   ├── document_agent.py    # Company document Q&A agent
│       │   └── general_agent.py     # General assistant fallback
│       ├── adapters/                # Pluggable data adapters
│       │   ├── __init__.py
│       │   ├── base.py              # DataAdapter abstract base class
│       │   ├── registry.py          # Adapter discovery and registry
│       │   └── gmail_adapter.py     # Gmail email attachment adapter
│       ├── providers/               # AI provider abstractions
│       │   ├── __init__.py
│       │   ├── base.py              # AI provider abstract factory
│       │   ├── openai_provider.py   # OpenAI SDK adapter
│       │   └── bedrock_provider.py  # AWS Bedrock adapter
│       ├── processors/              # Data processing utilities
│       │   ├── __init__.py
│       │   ├── excel_processor.py   # Excel parsing and validation
│       │   └── document_processor.py # PDF/image/text chunking
│       ├── tools/                   # Agent tool functions
│       │   ├── __init__.py
│       │   ├── analytics_tools.py   # Structured query execution tools
│       │   ├── cms_tools.py         # CMS API client tools
│       │   ├── tag_tools.py         # Tag matching and embedding tools
│       │   └── document_tools.py    # Document retrieval tools
│       ├── models/                  # SQLAlchemy models
│       │   ├── __init__.py
│       │   ├── document.py          # documents table model
│       │   ├── tag.py               # tags table model
│       │   ├── user.py              # users table model
│       │   ├── conversation.py      # conversations + messages models
│       │   └── summary.py           # Pre-computed analytics summaries
│       ├── schemas/                 # Pydantic request/response schemas
│       │   ├── __init__.py
│       │   ├── chat.py              # Chat API schemas
│       │   ├── ingestion.py         # Ingestion API schemas
│       │   ├── analytics.py         # Structured query schemas
│       │   └── documents.py         # Document upload schemas
│       ├── services/                # Business logic services
│       │   ├── __init__.py
│       │   ├── chat_service.py      # Conversation management
│       │   ├── ingestion_service.py # Excel ingestion pipeline
│       │   ├── embedding_service.py # Embedding generation (all-MiniLM-L6-v2)
│       │   ├── summary_service.py   # Pre-computed summary generation
│       │   └── auth_service.py      # Authentication (local + AD)
│       ├── api/                     # FastAPI routers
│       │   ├── __init__.py
│       │   ├── chat.py              # POST /chat, GET /conversations
│       │   ├── ingestion.py         # POST /ingest, GET /ingestion/status
│       │   ├── documents.py         # POST /documents/upload
│       │   ├── health.py            # GET /health, /health/agents
│       │   └── auth.py              # POST /auth/login, /auth/token
│       ├── tasks/                   # Celery async tasks
│       │   ├── __init__.py
│       │   ├── celery_app.py        # Celery application config
│       │   ├── email_monitor.py     # Gmail polling task
│       │   ├── excel_ingest.py      # Excel processing task
│       │   ├── document_ingest.py   # Document processing task
│       │   ├── summary_compute.py   # Summary recomputation task
│       │   └── folder_watch.py      # Watched folder monitoring task
│       └── db/                      # Database utilities
│           ├── __init__.py
│           ├── session.py           # Async SQLAlchemy session factory
│           └── migrations/          # Alembic migrations
├── tests/
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/
│   │   ├── test_excel_processor.py
│   │   ├── test_analytics_tools.py
│   │   ├── test_tag_tools.py
│   │   └── test_agents/
│   ├── integration/
│   │   ├── test_ingestion_pipeline.py
│   │   ├── test_chat_flow.py
│   │   └── test_document_pipeline.py
│   └── contract/
│       ├── test_data_adapter.py
│       └── test_ai_provider.py
├── alembic/                         # Alembic config and migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
├── docker-compose.yml               # PostgreSQL, Redis, app
├── Dockerfile
├── pyproject.toml                   # Project config, dependencies
├── .env.example                     # Environment variable template
└── watched_documents/               # Watched folder for document ingestion
```

**Structure Decision**: Backend-only web application structure under `backend/`. No frontend directory. The `tools/` directory is added to separate agent tool functions from core business services, following the Strands Agents SDK pattern where tools are registered with agents.

## Complexity Tracking

No constitution violations to justify. All principles are naturally aligned with the architecture.
