graph TD
    subgraph "1. Request Classification & Guardrails"
        U[User Prompt] -->|POST /chat| API[FastAPI Orchestrator]
        API --> IP[Hybrid Intent Parser: spaCy + OpenAI]
        IP --> CLASS{Intent Classifier}
        
        CLASS -->|Irrelevant/Out of Scope| GR[Guardrail: Polite Rejection]
        CLASS -->|Relevant| CM[ColumnMapper & Metadata Lookup]
    end

    subgraph "2. Multi-Route Query Planner"
        CM --> PLAN{Planner Logic}
        
        %% Route A: Simple Aggregation
        PLAN -- "Quantitative (How many...)" --> SQL[Route A: Safe SQL Executor]
        
        %% Route B: Consultative/Insight
        PLAN -- "Insight (When is best...)" --> INSIGHT[Route B: Analytical Insight Engine]
        
        %% Route C: Future Knowledge Base
        PLAN -- "Document/Policy (How do I...)" --> DOCS[Route C: pgvector Doc Retriever]
    end

    subgraph "3. Unified Data Layer (Postgres + pgvector)"
        SQL --> DB[(Postgres Data)]
        INSIGHT -->|Step 1: Get Pattern Data| DB
        DOCS -->|Step 2: Vector Search| DB
    end

    subgraph "4. Response Synthesis"
        SQL -->|Raw Data| COMP[LLM Composer]
        INSIGHT -->|Trend Analysis| COMP
        DOCS -->|Text Evidence| COMP
        
        COMP -->|Verified Answer + Data Citations| OUT[Final Response]
    end

    style GR fill:#ffcccc,stroke:#cc0000
    style INSIGHT fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style DB fill:#336791,color:#fff