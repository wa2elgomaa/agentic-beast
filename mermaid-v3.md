graph TD
  subgraph "1. Ingress & Orchestration"
    U[User Prompt] -->|POST /chat| API[FastAPI Orchestrator]
    API --> ChatSvc[Chat Service -attach conversation_history-]
    ChatSvc --> ORCH[Orchestrator]
    ORCH --> IC[Intent Classifier — Ollama -JSON-mode-]
    IC -->|Irrelevant / OOS| GR[Guardrail: Polite Rejection]
    IC -->|Relevant| CM[Column Mapper & Metadata Lookup]
    CM --> IP[Intent Parser → StructuredQueryObject]
    IP --> Router[Planner / Router]
  end

  subgraph "2. Routing & Execution"
    Router -- "Quantitative (How many...)" --> SQL[Safe SQL Executor -DB functions-]
    Router -- "Insight (When to post...)" --> AGT[Analytics Agent -parse → impl → format-]
    Router -- "Docs / KB" --> DOCS[pgvector Retriever]
    SQL --> DB[(Postgres + pgvector)]
    AGT --> DB
    DOCS --> DB
  end

  subgraph "3. Grounding & Response"
    SQL --> Composer[Grounded Composer -inject real rows; no numeric invention-]
    AGT --> Composer
    DOCS --> Composer
    Composer --> OUT[Final Response + Data Citations]
  end

  subgraph "4. Admin Ingestion"
    Admin[Admin / Watcher] --> Ingest[Ingestion Service]
    Ingest --> Transform[Transform, Validate, Normalize Metrics]
    Transform --> DB
  end

  style GR fill:#ffdddd,stroke:#cc0000
  style AGT fill:#e8f3ff,stroke:#1b6fb8,stroke-width:2px
  style DB fill:#2b6f93,color:#fff
  classDef smallFont font-size:12px;
  class ChatSvc,ORCH,IC,CM,IP,Router smallFont;