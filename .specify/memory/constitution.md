<!--
  === Sync Impact Report ===
  === Sync Impact Report ===
  Version change: 1.0.0 -> 1.2.0
  Modified principles: N/A (no principle changes)
  Modified sections:
    - Technology Stack Constraints:
      - Scheduling: APScheduler -> Celery Beat
      - Agent Tooling -> Agent Framework: LangChain (full) ->
        Strands Agents SDK (primary) + LangChain (text splitters only)
    - Code Organization:
      - Added tools/ directory for agent tool functions
  Added sections: N/A
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ aligned
    - .specify/templates/spec-template.md ✅ aligned
    - .specify/templates/tasks-template.md ✅ aligned
  Artifacts updated:
    - specs/001-agentic-ai-assistant/tasks.md ✅ updated
      (T008 partitioning, T020 Redis state, T062a tag embeddings,
       T064-T066 observability, T002 deps)
    - specs/001-agentic-ai-assistant/spec.md ✅ updated
      (edge cases resolved with concrete handling strategies)
  Follow-up TODOs: None
-->

# Agentic Beast Constitution

## Core Principles

### I. Pluggable Adapter Architecture

All external data sources MUST integrate through the standardized
`DataAdapter` abstract interface. No agent or service may directly
couple to a specific data source implementation.

- Every adapter MUST implement the base `DataAdapter` contract
  defined in `backend/src/app/adapters/`.
- Adapters MUST be discoverable via the adapter registry.
- Adding a new data source MUST NOT require modifications to
  existing agents or orchestration logic.
- Adapter configuration MUST be externalized (environment
  variables or config files), never hard-coded.

**Rationale**: The pluggable pattern enables future integration of
social media APIs, MongoDB, and other sources without architectural
changes.

### II. Agent Autonomy with Orchestration

Each agent MUST be independently testable, deployable, and
functional. The `AgentOrchestrator` coordinates but does not
subsume agent responsibilities.

- Every agent MUST expose a well-defined capability interface
  that the orchestrator can discover and route to.
- Agents MUST NOT directly invoke other agents; all inter-agent
  communication MUST flow through the orchestrator or a shared
  message bus.
- Agent state MUST be managed through the shared state
  management system (Redis), not local in-memory state.
- Each agent MUST handle its own error recovery and expose
  health status to the orchestrator.

**Rationale**: Autonomous agents enable parallel development,
independent testing, and graceful degradation when individual
agents fail.

### III. Multi-Provider AI Abstraction

All AI provider integrations MUST go through an abstract factory
pattern. No business logic may directly import provider-specific
SDKs.

- The AI adapter factory in `backend/src/app/providers/` MUST
  support OpenAI and AWS Bedrock as first-class providers.
- Provider switching MUST be achievable through configuration
  alone, with zero code changes in agents or services.
- All provider-specific error handling MUST be encapsulated
  within the provider adapter, exposing a unified error model
  to consumers.

**Rationale**: Provider abstraction prevents vendor lock-in and
enables cost optimization by routing requests to different
providers based on capability or pricing.

### IV. Async-First Processing

All I/O-bound operations MUST use async patterns. Blocking calls
are prohibited in the request path.

- FastAPI endpoints MUST use `async def` for any operation
  involving database, network, or file I/O.
- Long-running tasks (email processing, Excel parsing, bulk
  ingestion) MUST be delegated to Celery workers.
- Database operations MUST use async drivers (asyncpg for
  PostgreSQL).
- WebSocket connections for real-time agent communication MUST
  use native async handling.

**Rationale**: Async processing is essential for handling
concurrent agent operations and maintaining responsiveness
during data ingestion pipelines.

### V. Structured Observability

All agents, adapters, and services MUST emit structured logs
and expose operational metrics.

- All components MUST use `structlog` for structured JSON
  logging with correlation IDs.
- Every agent execution MUST log: start, completion, duration,
  and outcome (success/failure with error classification).
- Data ingestion pipelines MUST track: records processed,
  records failed, processing duration, and data quality scores.
- Health check endpoints MUST be exposed for every agent and
  critical service.

**Rationale**: A multi-agent system with background processing
pipelines requires deep observability to diagnose issues across
distributed workflows.

### VI. Data Integrity and Schema Validation

All data entering the system MUST be validated against defined
schemas before persistence. Data pipelines MUST guarantee
idempotent processing.

- Excel report ingestion MUST validate column mappings against
  the expected schema before inserting into `documents`.
- All Pydantic V2 models MUST enforce strict validation mode.
- Database migrations MUST be managed through Alembic with
  no manual schema changes permitted.
- Daily data ingestion MUST be idempotent: re-processing the
  same report for the same date MUST NOT create duplicates.

**Rationale**: Automated data pipelines processing email
attachments are inherently fragile; strict validation prevents
corrupt data from propagating through analytics.

### VII. Incremental Delivery

Every feature MUST be deliverable as an independent, testable
slice that adds user-visible value.

- Each user story MUST be independently implementable and
  testable without requiring completion of other stories.
- The Gmail adapter and Excel processor form the MVP and
  MUST be fully functional before other agents are built.
- Integration tests MUST cover the complete pipeline for
  each delivered slice (email receipt through database
  persistence).
- Each agent MUST be deployable and useful on its own before
  multi-agent collaboration features are added.

**Rationale**: The system's complexity demands incremental
validation; delivering working slices reduces risk and enables
early feedback.

## Technology Stack Constraints

The following technology choices are binding decisions. Deviations
require a constitution amendment.

- **Runtime**: Python 3.11+ with FastAPI (async/await, WebSocket)
- **Database**: PostgreSQL 15+ with table partitioning for
  time-series data and pgvector for embeddings
- **Cache/State**: Redis for agent state management and caching
- **Task Queue**: Celery for background email processing and
  bulk data ingestion
- **AI Providers**: OpenAI SDK + Boto3 (AWS Bedrock) through
  the abstract provider factory
- **Data Processing**: Pandas + Openpyxl for Excel manipulation;
  Gmail API Client for email integration
- **Agent Framework**: AWS Strands Agents SDK for agent
  orchestration, tool registration, and memory management;
  LangChain limited to text splitters and document processing
  utilities only; Pydantic V2 for all data validation
- **Scheduling**: Celery Beat for automated email monitoring
  and periodic task scheduling
- **Observability**: Structlog (logging), Prometheus + Grafana
  (metrics), Sentry (error tracking)
- **Migrations**: Alembic for all database schema changes
- **Containerization**: Docker Compose for local development

## Development Workflow

### Code Organization

All code MUST follow the established project structure:

```
backend/src/app/
  agents/       # One file per agent
  adapters/     # One file per data adapter
  providers/    # One file per AI provider
  processors/   # Data processing utilities
  tools/        # Agent tool functions (Strands SDK pattern)
  models/       # SQLAlchemy/Pydantic models
  schemas/      # API request/response schemas
  services/     # Business logic services
```

### Quality Gates

- All PRs MUST pass: linting, type checking, and existing tests.
- New adapters MUST include contract tests validating the
  `DataAdapter` interface.
- New agents MUST include unit tests with mocked AI providers.
- Integration tests MUST cover end-to-end data flow for any
  pipeline change.
- API endpoints MUST have OpenAPI documentation auto-generated
  from Pydantic schemas.

### Environment Management

- All configuration MUST be managed through environment variables
  with Pydantic Settings.
- Secrets (API keys, OAuth tokens) MUST NOT appear in code or
  configuration files.
- Docker Compose MUST provide a complete local development
  environment with all dependencies.

## Governance

This constitution is the authoritative source for architectural
decisions and development standards for the Agentic Beast project.
All implementation work MUST comply with the principles defined
above.

- **Amendment process**: Any principle change MUST be documented
  with rationale, reviewed, and reflected in a version bump.
  Amendments that remove or redefine principles require a MAJOR
  version increment.
- **Versioning**: This constitution follows semantic versioning.
  MAJOR for incompatible governance changes, MINOR for new
  principles or expanded guidance, PATCH for clarifications.
- **Compliance review**: Every feature specification and
  implementation plan MUST include a Constitution Check section
  verifying alignment with these principles.
- **Guidance file**: Runtime development guidance beyond this
  constitution resides in project documentation under `docs/`.

**Version**: 1.1.0 | **Ratified**: 2026-03-05 | **Last Amended**: 2026-03-05
