# AI Assistant Platform with Agentic Architecture & Pluggable Data Adapters — REFINED PLAN

TL;DR  
Refine the original plan to incorporate decisions from our conversation:
- Offline-first deployment option (local LLMs, on-disk vector DBs)
- RAG orchestration via RagFlow for ingestion/query pipelines
- Deterministic analytics via structured query objects + safe executor (C + B), with RAG (A) and precomputed summaries (D) as augmentations
- Daily ETL and incremental embedding upserts
- Strong safety, auditability, and schema/metadata-first design

This document replaces/enhances the previous plan and maps requirements to concrete deliverables, milestones, acceptance criteria, and an operational flow diagram.

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
Paths are suggestions in repository `backend/src/app/`:

- Adapters
  - backend/src/app/adapters/base.py  — DataAdapter interface
  - backend/src/app/adapters/gmail_adapter.py — Gmail attachment ingestion (OAuth2)
  - backend/src/app/adapters/local_file_adapter.py — simple file upload adapter
- Processors
  - backend/src/app/processors/excel_processor.py — canonicalize, parse dates, add month/year, create row_summary
  - backend/src/app/processors/validation.py — schema checks & PII redaction
- Agents & Orchestrator
  - backend/src/app/agents/orchestrator.py — AgentOrchestrator core
  - backend/src/app/agents/data_ingestion_agent.py
  - backend/src/app/agents/analytics_agent.py — builds structured queries, calls executor
  - backend/src/app/agents/document_agent.py — RAG retrieval over docs
- Analytics Executor
  - backend/src/app/analytics/executor.py — safe executor for structured query objects (no raw SQL)
  - backend/src/app/analytics/schema.json — JSON Schema for structured query objects
- Retrieval & Embeddings
  - backend/src/app/retrieval/vector_store.py — Chroma/FAISS wrapper with upsert/query
  - backend/src/app/retrieval/embeddings.py — sentence-transformers wrapper + version metadata
- NLP & Mapping
  - backend/src/app/nlp/intent_parser.py — spaCy NER + heuristics
  - backend/src/app/nlp/column_mapper.py — fuzzy mapping + synonyms registry
- LLM Adapters
  - backend/src/app/providers/openai_provider.py
  - backend/src/app/providers/bedrock_provider.py
  - backend/src/app/providers/local_llm_provider.py
  - backend/src/app/providers/factory.py — returns provider instance
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

Milestone 0 — Bootstrap & infra (Week 0.5)
- Tasks:
  - Initialize repo structure, dependencies, docker-compose (FastAPI, Chroma/FAISS optional, DB)
  - Create requirements / base Dockerfile
  - Add SPECKIT_CONSTITUTION.md
- Acceptance:
  - `docker-compose up` starts services; `uvicorn app.api.main:app` health check OK

Milestone 1 — Ingestion & Data Adapters (Weeks 1–2)
- Tasks:
  - Implement DataAdapter base + GmailAdapter (OAuth2 skeleton)
  - Implement ExcelProcessor: canonicalization, datetime parsing, row_summary creation, PII redaction
  - Implement local-file adapter for manual uploads
  - Route ingests into processed.parquet and metadata.json
- Acceptance:
  - `scripts/ingest.py --excel data/sample.xlsx` writes processed.parquet and metadata.json
  - `pytest tests/test_gmail_adapter.py` passes (mocks acceptable)

Milestone 2 — Embeddings & Vector Store (Week 2)
- Tasks:
  - Implement embeddings module using sentence-transformers and store model version
  - Implement vector_store wrapper (Chroma/FAISS) with upsert/query/persist
  - Implement incremental upsert for new rows
- Acceptance:
  - After ingest, `vector_store.query("sample text")` returns related rows
  - Vector DB directory persists and can be snapshotted

Milestone 3 — Structured Query Schema & Safe Executor (Week 3)
- Tasks:
  - Define JSON Schema for structured queries (metric, op, group_by, filters, time_window, top_n)
  - Implement executor that validates against schema and executes only whitelisted columns/ops
  - Add unit tests with expected numeric outputs
- Acceptance:
  - `pytest tests/test_executor.py` validates results against sample data
  - Attempted raw-SQL or disallowed op rejected by executor

Milestone 4 — Intent Parsing, Column Mapping & Planner (Week 4)
- Tasks:
  - Implement spaCy-based IntentParser and ColumnMapper (thefuzz/fuzzy matching)
  - Implement QueryPlanner: choose materialized view (D) vs executor (B)
  - Add synonyms registry and metadata lookup
- Acceptance:
  - Example prompt -> structured query object produced (validated by schema)
  - Planner chooses materialized view if available (unit tests)

Milestone 5 — Retrieval + LLM Composer + Providers (Week 5)
- Tasks:
  - Implement Retriever wrapper and evidence selection logic (top-k + metadata)
  - Implement Composer using provider factory (OpenAI / Bedrock / Local)
  - Compose template that feeds deterministic result + evidence into LLM for explanation
- Acceptance:
  - End-to-end: prompt returns deterministic numeric result + LLM explanation + evidence
  - Logs include data_version & model_version in response metadata

Milestone 6 — Orchestrator, API, and RagFlow Integration (Weeks 6–7)
- Tasks:
  - Implement AgentOrchestrator to sequence steps for /chat
  - Wire RagFlow YAML for ingestion and scheduled upserts; test offline run
  - Integrate orchestrator with FastAPI /chat endpoint
- Acceptance:
  - `curl /chat` returns expected result for sample prompts
  - RagFlow ingestion run successfully updates vector DB and materialized views

Milestone 7 — Hardening, Security, & Ops (Weeks 8–9)
- Tasks:
  - Add authentication for /chat (API keys)
  - Implement logging, metrics (Prometheus) and retention policies
  - Add backup snapshots for vector DB & materialized views
  - Add CI checks & integration tests
- Acceptance:
  - Automated ETL runs without manual intervention; alert on failures
  - CI passes on PRs; deployable Docker artifacts produced

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

## 10. Next immediate actions (pick 3)
1. Scaffold repo with directories and CI + Docker compose (Milestone 0).  
2. Implement `DataAdapter` base + `ExcelProcessor` + `create_dataset.py` (Milestone 1).  
3. Implement structured query schema and a minimal safe executor that runs example prompts against sample Excel (Milestone 3).

