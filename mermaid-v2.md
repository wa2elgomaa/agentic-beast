graph TD

  subgraph "1 — Ingress & Orchestration"
    U[User Prompt] -->|POST /chat| API[FastAPI]
    API --> ChatSvc["Chat Service\n(attach conversation_history)"]
    ChatSvc --> ORCH[AgentOrchestrator]
    ORCH --> IC["Intent Classifier\nOllama · JSON-mode"]
    IC -->|unknown| GR["Guardrail\n(polite rejection)"]
    IC -->|analytics| APATH[Analytics Path]
    IC -->|tag_suggestions| TPATH[Tag Suggestions Path]
    IC -->|article_recommendations| DPATH[Article Recommendations Path]
  end

  subgraph "2 — Analytics Path  (primary)"
    APATH --> SQLGEN["SQL Generator\nOllama deepseek-coder\n→ {sql, params, metric,\n   operation, query_category}"]
    SQLGEN --> DBQT["dbquery_tool\n(validate · execute · cap rows)"]
    DBQT -->|success| RESP["response_agent\n(rows → AnalyticsResponseContent)"]
    DBQT -->|SQL error| RETRY{"Retry?\nmax 2×"}
    RETRY -->|yes — inject error_hint| SQLGEN
    RETRY -->|no — exhausted| FALLBACK["Fallback: pre-built\nanalytics tools\n(DB _impl functions)"]
    FALLBACK --> RESP
  end

  subgraph "3 — Other Paths"
    TPATH --> TAGAGENT["Tagging Agent\n(Strands)"]
    DPATH --> DOCAGENT["Doc QA Agent\n(Strands · pgvector)"]
  end

  subgraph "4 — Unified Data Layer"
    DBQT -->|readonly · parameterized| DB[("PostgreSQL\n+ pgvector\n(documents table)")]
    FALLBACK --> DB
    TAGAGENT --> DB
    DOCAGENT --> DB
  end

  subgraph "5 — Response"
    RESP --> OUT["Final Response\n(AnalyticsResponseContent)\nresult_data + insight_summary\n+ verification"]
    TAGAGENT --> OUT
    DOCAGENT --> OUT
    GR --> OUT
  end

  subgraph "6 — Admin Ingestion"
    ADM["Admin / Watcher"] --> ING["Ingestion Service"]
    ING --> XFORM["Transform · Validate\nNormalise Metrics"]
    XFORM --> DB
  end

  style GR fill:#ffdddd,stroke:#cc0000
  style RESP fill:#e8f3ff,stroke:#1b6fb8,stroke-width:2px
  style DB fill:#2b6f93,color:#fff
  style RETRY fill:#fff8e1,stroke:#f9a825

  classDef small font-size:11px
  class ChatSvc,IC,SQLGEN,DBQT,FALLBACK,TAGAGENT,DOCAGENT,ING,XFORM small