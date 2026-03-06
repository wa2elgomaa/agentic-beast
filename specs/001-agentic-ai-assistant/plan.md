# Implementation Plan: Agentic AI Assistant Platform

**Branch**: `001-agentic-ai-assistant` | **Date**: 2026-03-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-agentic-ai-assistant/spec.md`

## Summary

Build a multi-agent AI assistant platform with pluggable data adapters, prioritizing Gmail Excel report ingestion and analytics querying. The system uses AWS Strands Agents SDK for agentic orchestration, a hybrid data access layer (structured query objects + tool functions + RAG + pre-computed summaries), and supports multiple AI providers (OpenAI + AWS Bedrock). REST API only; no frontend in scope.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, Strands Agents SDK, LangChain, Pydantic V2, SQLAlchemy (async), Celery, Redis, Pandas, Openpyxl
**Storage**: PostgreSQL 15+ (pgvector, table partitioning), MongoDB (articles via CMS/direct), Redis (agent state/cache)
**Testing**: pytest, pytest-asyncio, pytest-httpx (for CMS API mocking)
**Target Platform**: Linux server (Docker Compose for local dev, AWS for production)
**Project Type**: web-service (API-only, no frontend)
**Performance Goals**: Analytics queries <10s for 1 year of daily data; Excel ingestion <2min for 10k rows
**Constraints**: API-only (no frontend), local-first development, async-first I/O, idempotent data ingestion
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
