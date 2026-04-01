# AI Assistant Platform with Agentic Architecture & Pluggable Data Adapters — REFINED PLAN

> **Last updated: 2026-03-31**  
> Implementation is in progress. See §0-A for current status.

TL;DR  
Refine the original plan to incorporate decisions from our conversation:
- Offline-first deployment option (local LLMs, on-disk vector DBs)
- RAG orchestration via RagFlow for ingestion/query pipelines
- Deterministic analytics via structured query objects + safe executor (C + B), with RAG (A) and precomputed summaries (D) as augmentations
- Daily ETL and incremental embedding upserts
- Strong safety, auditability, and schema/metadata-first design

This document replaces/enhances the previous plan and maps requirements to concrete deliverables, milestones, acceptance criteria, and an operational flow diagram.

---

## 0-A. Implementation Status (as of 2026-03-31)

### ✅ Platform Foundation (Milestones 0–2 — fully delivered)

| Component | File(s) | Status |
|-----------|---------|--------|
| FastAPI app with `/chat` endpoint | `backend/src/app/api/` | ✅ Live |
| Agent orchestrator (Strands Swarm pattern) | `backend/src/app/agents/orchestrator.py` | ✅ Live |
| Analytics agent (Strands `Agent`) | `backend/src/app/agents/analytics_agent.py` | ✅ Live |
| Ingestion agent | `backend/src/app/agents/ingestion_agent.py` | ✅ Live |
| Tagging agent | `backend/src/app/agents/tagging_agent.py` | ✅ Live |
| AI provider factory (OpenAI / Bedrock / Ollama) | `backend/src/app/agents/agent_factory.py` | ✅ Live |
| Ollama provider & Strands provider | `backend/src/app/providers/` | ✅ Live |
| PostgreSQL + SQLAlchemy async models | `backend/src/app/models/document.py` | ✅ Live |
| Alembic migrations | `backend/alembic/` | ✅ Live |
| SQLAlchemy analytics DB tools | `backend/src/app/tools/analytics_db_function_tools.py` | ✅ Live |
| Sentence-transformer embeddings | `backend/src/app/services/embedding_service.py` | ✅ Live |
| pgvector vector search | `backend/src/app/models/document.py` | ✅ Live |
| spaCy intent classifier | `backend/src/app/utilities/intent_classifier.py` | ✅ Live |
| Redis + Celery background tasks | `docker-compose.yml` | ✅ Live |
| Prometheus + Grafana observability | `backend/prometheus.yml`, `backend/grafana/` | ✅ Live |
| Next.js frontend with auth & chat UI | `frontend/` | ✅ Live |
| Docker Compose full-stack setup | `docker-compose.yml` | ✅ Live |

### ✅ Anti-Hallucination Pipeline (implemented 2026-03-31)

Root cause: `mistral:7b` on Ollama has no function-calling or JSON mode — it generates training-data templates (`<highest_video_title>`, `Video ID 1`) instead of real values. Fix: pre-execution pattern where Python runs SQL before the LLM sees any data.

| Phase | What changed | File | Status |
|-------|-------------|------|--------|
| 1 | Default Ollama model → `deepseek-coder:6.7b`; added `OLLAMA_NUM_CTX: "4096"` | `docker-compose.yml` | ✅ Done |
| 2 | `METRIC_COLUMNS` 9→26 entries; `GROUP_BY_COLUMNS` 5→10 entries (matches `init.sql`) | `tools/analytics_db_function_tools.py` | ✅ Done |
| 3 | Created `column_mapper.py` — `DATA_DICTIONARY`, `WHITELISTED_METRICS` (18), `WHITELISTED_DIMENSIONS` (8), `resolve_column()` | `nlp/column_mapper.py` *(new)* | ✅ Done |
| 4 | Created `intent_parser.py` — `StructuredQueryObject` (Pydantic), `parse_query()` via Ollama `format=json` | `nlp/intent_parser.py` *(new)* | ✅ Done |
| 5 | Added `run_analytics_query()` — parse → SQL → grounded summary (LLM never generates numbers) | `agents/analytics_agent.py` | ✅ Done |
| 6 | Added `_value_guard()` — rejects LLM response if any number ≥ 100 not present in DB rows | `agents/orchestrator.py` | ✅ Done |
| 7 | Analytics intents routed through `run_analytics_query()` instead of bare Strands agent | `agents/orchestrator.py` | ✅ Done |
| 8 | `complex()` fallback replaced: Ollama `format=json` → `{"intent": "<label>"}` (no free-text) | `utilities/intent_classifier.py` | ✅ Done |

**How the pre-execution pipeline works (Phase 5):**
```
user message
    │
    ▼
parse_query()  ──→  Ollama /api/chat  format=json
    │               constrains output to StructuredQueryObject JSON
    │
    ▼
StructuredQueryObject  (metric whitelist validated by Pydantic)
    │
    ▼
get_top_content_db_impl()  or  query_metrics_db_impl()   ← pure SQLAlchemy
    │
    ▼
real DB rows  ──→  _build_insight_summary()  ← numbers formatted in Python
    │
    ▼
Response dict  (LLM never touched a single number)
    │
    ▼
_value_guard()  ← final sanity check: rejects if invented numbers detected
```

### 🔄 Remaining / In-progress

| Area | Status | Notes |
|------|--------|-------|
| Gmail adapter (OAuth2) | ⏳ Pending | Milestone 1 |
| Incremental embedding upserts (delta ingest) | ⏳ Pending | Milestone 2 |
| Materialized daily/monthly views | ⏳ Pending | Milestone 3 |
| Query planner (materialized vs live SQL) | ⏳ Pending | Milestone 4 |
| Evidence retrieval + LLM composer for analytics | ⏳ Pending | Milestone 5 |
| RagFlow ingestion YAML | ⏳ Pending | Milestone 6 |
| API key auth hardening | ⏳ Pending | Milestone 7 |
| Audit log (query → result → LLM output) | ⏳ Pending | Milestone 7 |
| Rebuild container with `deepseek-coder:6.7b` | ⏳ Pending | Run: `docker compose build app && docker compose up -d ollama app` |

---

## 0. Key Requirements (derived & explicit)
- Accuracy: numeric answers must come from deterministic computations (Pandas / SQL / materialized views).
- Flexibility: support natural-language questions over company documents + analytics (RAG + analytics).
- Offline capability: option to run fully offline (local embedding and LLM stacks).
- Multi-provider AI: plug-in adapters for OpenAI and AWS Bedrock (and a local LLM adapter).
- Safety: no raw SQL or arbitrary code executed from LLM output. Use structured query objects validated by a whitelist.
- Daily refresh: ingest daily Excel reports (Gmail attachments) and upsert only deltas to embeddings index.
- Observability & auditing: log prompt → structured query → deterministic result → evidence → LLM output with data and model versions.
- Extensibility: pluggable data adapter model to add more sources later.

---

## 1. High-level Architecture (refined)
- Ingestion & ETL:
  - RagFlow ingestion pipelines (or Prefect/cron wrapper) to read Gmail attachments or upload Excel → canonicalized Parquet.
  - Produce materialized views (daily/monthly rollups) and a row-summary text for embeddings.
- Storage:
  - Processed data: Parquet (partitioned by ingest_date) and Postgres/Timescale or DuckDB for larger scale.
  - Vector DB: local FAISS/Chroma (offline) or managed Milvus/Weaviate for scale.
  - Metadata catalog: metadata.json (columns, types, synonyms), data_versioning.
- Execution & Orchestration:
  - AgentOrchestrator routes requests to:
    - IntentParser (spaCy / small classifier)
    - ColumnMapper (fuzzy matching + synonyms)
    - Structured Query Builder (JSON object)
    - Query Planner -> determines D (materialized) vs B (executor)
    - Deterministic Executor (Pandas / DuckDB / SQL) — safe layer
    - Retriever (vector DB) for evidence
    - Composer (LLM) for presentation/explanation
- AI Provider Layer:
  - Adapter factory supports OpenAI, AWS Bedrock, and Local LLM adapter (Ollama / Llama cpp).
- API:
  - FastAPI with /chat, internal-only / secure + WebSocket optional.
- Ops:
  - Scheduler for ETL (RagFlow or Prefect), backups and snapshots for vector DB and materialized views, CI tests.

---

## 2. Concrete Deliverables (file & module view)
Paths relative to `backend/src/app/`. ✅ = implemented, 📐 = planned.

- Adapters
  - 📐 backend/src/app/adapters/base.py  — DataAdapter interface
  - 📐 backend/src/app/adapters/gmail_adapter.py — Gmail attachment ingestion (OAuth2)
  - 📐 backend/src/app/adapters/local_file_adapter.py — simple file upload adapter
- Processors
  - 📐 backend/src/app/processors/excel_processor.py — canonicalize, parse dates, add month/year, create row_summary
  - 📐 backend/src/app/processors/validation.py — schema checks & PII redaction
- Agents & Orchestrator
  - ✅ backend/src/app/agents/orchestrator.py — AgentOrchestrator (Strands Swarm pattern) + `_value_guard()`
  - ✅ backend/src/app/agents/ingestion_agent.py
  - ✅ backend/src/app/agents/analytics_agent.py — pre-execution pipeline (`run_analytics_query()`)
  - ✅ backend/src/app/agents/tagging_agent.py
  - 📐 backend/src/app/agents/document_agent.py — RAG retrieval over docs
- Analytics Executor
  - ✅ backend/src/app/tools/analytics_db_function_tools.py — SQL-backed Strands `@tool` functions (safe, no raw SQL)
  - 📐 backend/src/app/analytics/schema.json — formal JSON Schema for structured query objects
- Retrieval & Embeddings
  - ✅ backend/src/app/services/embedding_service.py — sentence-transformers + pgvector
  - 📐 backend/src/app/retrieval/vector_store.py — Chroma/FAISS wrapper with upsert/query
- NLP & Mapping
  - ✅ backend/src/app/nlp/intent_parser.py — `parse_query()` via Ollama `format=json`, `StructuredQueryObject` (Pydantic)
  - ✅ backend/src/app/nlp/column_mapper.py — `DATA_DICTIONARY`, `WHITELISTED_METRICS/DIMENSIONS`, `resolve_column()`
  - ✅ backend/src/app/utilities/intent_classifier.py — spaCy keyword fast-path + Ollama JSON-mode fallback
- LLM Adapters
  - ✅ backend/src/app/providers/openai_provider.py
  - ✅ backend/src/app/providers/ollama_provider.py
  - ✅ backend/src/app/providers/strands_provider.py
  - ✅ backend/src/app/providers/factory.py — returns provider instance
  - 📐 backend/src/app/providers/bedrock_provider.py
- API & CLI
  - backend/src/app/api/main.py — FastAPI app with `/chat` and health
  - backend/src/app/cli/ingest_cli.py — manual ingestion utilities
- Ingestion Pipelines & Automation
  - ragflow/pipelines/analytics_pipeline.yaml — ingestion + embed upserts
  - dag/cron/prefect flows for offline deployments
- Tests & CI
  - backend/tests/test_gmail_adapter.py
  - backend/tests/test_executor.py
  - backend/tests/test_intent_parser.py
  - .github/workflows/ci.yml (lint, pytest)
- Docs
  - docs/architecture_offline.md (include mermaid flow)
  - SPECKIT_CONSTITUTION.md (principles)
  - README.md (developer quick start)

---

## 3. Refined Step-by-step Plan & Milestones

Milestone 0 — Bootstrap & infra ✅ COMPLETE
- Tasks:
  - ✅ Initialize repo structure, dependencies, docker-compose (FastAPI, PostgreSQL, Redis, pgvector)
  - ✅ Create requirements / base Dockerfile
  - ✅ Full-stack Docker Compose with Ollama, Prometheus, Grafana, MongoDB
- Acceptance:
  - ✅ `docker-compose up` starts all services; FastAPI health check OK

Milestone 1 — Ingestion & Data Adapters ⏳ PARTIAL
- Tasks:
  - ✅ Excel ingestion via `scripts/ingest_analytics.py` + `scripts/seed_analytics.py`
  - ✅ Local file upload adapter (basic)
  - ✅ PostgreSQL `documents` table with 30+ columns matching `init.sql`
  - ⏳ GmailAdapter (OAuth2 skeleton) — not yet implemented
  - ⏳ PII redaction processor — not yet implemented
- Acceptance:
  - ✅ `scripts/seed_analytics.py` writes analytics rows to `documents` table
  - ⏳ `pytest tests/test_gmail_adapter.py` — not yet written

Milestone 2 — Embeddings & Vector Store ✅ COMPLETE
- Tasks:
  - ✅ sentence-transformers embedding service with pgvector storage
  - ✅ Incremental upsert via `beast_uuid` stable row identifier
  - ✅ `Document.embedding` Vector(384) column
- Acceptance:
  - ✅ Embeddings stored in `documents.embedding`; pgvector similarity search available

Milestone 3 — Structured Query Schema & Safe Executor ✅ COMPLETE
- Tasks:
  - ✅ `StructuredQueryObject` Pydantic model with whitelisted metric/operation/dimension validation
  - ✅ `parse_query()` — calls Ollama `format=json` to produce validated structured query
  - ✅ SQL-backed safe executor (`analytics_db_function_tools.py`) — no raw SQL from LLM
  - ✅ `METRIC_COLUMNS` (26 entries) and `GROUP_BY_COLUMNS` (10 entries) matching `init.sql`
  - ✅ `WHITELISTED_METRICS` (18) and `WHITELISTED_DIMENSIONS` (8) in `column_mapper.py`
  - ✅ `_value_guard()` — numeric hallucination detection
- Acceptance:
  - ✅ Non-whitelisted metric (`revenue`) nulled by Pydantic validator
  - ✅ Invented numbers rejected by `_value_guard()`
  - ✅ All safe_executor tests pass locally

Milestone 4 — Intent Parsing, Column Mapping & Planner ✅ COMPLETE
- Tasks:
  - ✅ `IntentClassifier` — spaCy keyword fast-path + Ollama JSON-mode fallback (`complex()`)
  - ✅ `ColumnMapper` (`column_mapper.py`) — synonym dict + `resolve_column()`
  - ✅ `parse_query()` (`intent_parser.py`) — structured query parser via Ollama `format=json`
  - ⏳ QueryPlanner (materialized view vs live SQL) — not yet implemented
- Acceptance:
  - ✅ spaCy → intent label; Ollama JSON fallback → `{"intent": "<label>"}`
  - ✅ Natural language term → canonical DB column via `resolve_column()`
  - ✅ `StructuredQueryObject` produced and whitelisted for any supported query

Milestone 5 — Retrieval + LLM Composer + Providers ⏳ PARTIAL
- Tasks:
  - ✅ Provider factory supports OpenAI, Ollama, Strands backends
  - ✅ Pre-execution pipeline: `run_analytics_query()` formats grounded response (no LLM numbers)
  - ⏳ Evidence retrieval (vector search → top-k passages appended to answer)
  - ⏳ Composer template feeding deterministic result + evidence into LLM explanation
  - ⏳ `data_version` & `model_version` in response metadata
- Acceptance:
  - ✅ Analytics responses contain only DB-sourced numbers
  - ⏳ Non-analytics document QA returns evidence citations

Milestone 6 — Orchestrator, API, and RagFlow Integration ⏳ PARTIAL
- Tasks:
  - ✅ `AgentOrchestrator.execute()` routes intents to specialist agents
  - ✅ Analytics intents routed through pre-execution pipeline with Value-Guard
  - ✅ FastAPI `/chat` wired to orchestrator
  - ⏳ RagFlow YAML ingestion pipeline
  - ⏳ Scheduled ETL / incremental embedding upserts
- Acceptance:
  - ✅ `curl /chat` returns grounded analytics result for supported queries
  - ⏳ RagFlow ingestion run completes without errors

Milestone 7 — Hardening, Security, & Ops ⏳ PARTIAL
- Tasks:
  - ✅ JWT-based auth on `/chat` (frontend auth context)
  - ✅ Prometheus metrics + Grafana dashboards deployed
  - ✅ Structlog async logging throughout
  - ⏳ Audit log: structured_query + data_version + result + LLM output per request
  - ⏳ Backup snapshots for vector DB & materialized views
  - ⏳ Full CI pipeline (lint + pytest + integration)
- Acceptance:
  - ✅ Authenticated users only; Prometheus scraping health metrics
  - ⏳ CI passes on PRs; audit log queryable

Pilot & Iterate (Weeks 10+)
- Onboard small user group, collect error logs and false positives, tune synonyms and intent prompts, expand materialized views for frequent queries.

---

## 4. Structured Query JSON Schema (example)
Use this schema to validate LLM-produced objects and for the safe executor:

```json
{
  "type": "object",
  "required": ["metric","operation"],
  "properties": {
    "metric": {"type":"string"},
    "operation": {"type":"string","enum":["sum","average","max","min","top_n","count"]},
    "group_by": {"type":["string","null"]},
    "filters": {
      "type":"object",
      "additionalProperties": {
        "anyOf":[
          {"type":"string"},
          {"type":"object","properties":{"from":{"type":"string"},"to":{"type":"string"}}}
        ]
      }
    },
    "time_window": {"type":"object","properties":{"from":{"type":"string"},"to":{"type":"string"}}},
    "top_n": {"type":"integer","minimum":1}
  },
  "additionalProperties": false
}
```

---

## 5. Data Flow (Mermaid diagram)
Include this in docs/architecture_offline.md and RagFlow docs.

```mermaid
flowchart TD
  subgraph INGEST
    G[GmailAdapter] --> I[Ingestion Job (RagFlow)]
    U[Upload Adapter] --> I
    I --> P[ExcelProcessor -> processed.parquet]
    P --> M[Materialize Views (monthly,daily)]
    P --> S[Row Summaries (text)]
    S --> E[Embedder (sentence-transformers)]
    E --> V[Vector Store (Chroma/FAISS)]
    P --> META[metadata.json (schema,synonyms,versions)]
  end

  subgraph QUERY
    Q[User prompt -> /chat] --> IP[IntentParser (spaCy)]
    IP --> CM[ColumnMapper (fuzzy)]
    CM --> BUILD[StructuredQuery Builder]
    BUILD --> PLAN{Planner: use materialized?}
    PLAN -- yes --> M
    PLAN -- no --> EXEC[Safe Executor (Pandas/DuckDB)]
    EXEC --> R[Deterministic Result]
    M --> R
    R --> RET[Retriever (Vector Store)]
    V --> RET
    RET --> COMP[Composer (LLM)]
    COMP --> RESP[Return {answer, result, evidence, provenance}]
  end

  subgraph OPS
    Sched[Scheduler (cron/Prefect/RagFlow)] --> I
    Snap[Snapshot/Backup] --> V
    Snap --> M
  end
```

---

## 6. Tech Stack (refined)
- API & Orchestration: FastAPI, asyncio, RagFlow, Prefect (optional)
- AI: OpenAI SDK, Boto3 (Bedrock), Local LLM adapters (Ollama / llama.cpp / transformers)
- Embeddings & Vector DB: sentence-transformers, Chroma/FAISS (local), Milvus/Weaviate (scale)
- Deterministic compute: Pandas / DuckDB / Postgres + pgvector (if using pgvector)
- Metadata & Schema: JSON + Pydantic V2
- Scheduler & Background: Prefect / cron / Celery (for heavy tasks)
- Storage: Parquet (data lake), Postgres partitioned for time-series (optional)
- Monitoring: Prometheus, Grafana, Structlog, Sentry

---

## 7. Security, Governance & Data Policies
- PII redaction at ingestion; hashed IDs stored when needed
- Access control on API: internal-only network + API tokens
- Audit logs for every chat: store structured_query, data_version, result, evidence IDs, LLM prompt & response
- Snapshot and retention policy for vector DB & materialized views
- Secrets stored in vault (HashiCorp Vault / AWS Secrets Manager)

---

## 8. Verification & Tests
- Unit tests: executor math & filter logic, intent parser slot extraction, column mapping
- Integration tests: ingest sample Excel -> embeddings -> query -> expected deterministic result
- Regression tests: canonical prompts and expected numeric outputs for each release
- Load tests: simulate many concurrent chat requests and ETL upserts

Example test commands:
- `pytest tests/test_executor.py`
- `python -m scripts/ingest_sample.py && pytest tests/integration/test_end_to_end.py`

---

## 9. Risks & Mitigations
- Risk: LLM hallucination in explanations → Mitigate: only show LLM output after deterministic verification and require explicit provenance block.
- Risk: Large Excel files slow embedding → Mitigate: chunking, selective column embedding, incremental upserts.
- Risk: Schema drift from new reports → Mitigate: schema detection rules, monitoring/alerts, and a fallback data review workflow.
- Risk: Offline LLM quality insufficient → Mitigate: hybrid provider strategy (local for sensitive, hosted for complex generation) and do canary testing

---

## 10. Next Immediate Actions

The anti-hallucination pipeline is complete. Priority order for what remains:

1. **Deploy the model change** — rebuild and restart containers so `deepseek-coder:6.7b` is pulled:
   ```bash
   docker compose build app && docker compose up -d ollama app
   # then wait for ollama to pull the model (~3.5 GB)
   ```

2. **Query Planner** (Milestone 4 gap) — implement `analytics/planner.py` that decides between  
   live SQL (`query_metrics_db_impl`) vs a pre-aggregated materialized view for common roll-ups  
   (daily/monthly totals). This will make high-frequency queries sub-second.

3. **Audit log** (Milestone 7) — add a `chat_audit_log` table (or append to a JSONL file) that  
   records: `user_message`, `structured_query`, `db_rows_count`, `insight_summary`, `model`,  
   `timestamp` for every analytics request. Wire into `run_analytics_query()`.

4. **Gmail adapter** (Milestone 1 gap) — implement OAuth2 skeleton for automated daily Excel  
   attachment ingestion so the data pipeline runs without manual uploads.

5. **Integration test suite** — add `tests/integration/test_analytics_pipeline.py` that seeds  
   known data rows and asserts exact numeric outputs from `run_analytics_query()`.

