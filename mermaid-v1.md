graph TD
    subgraph "1. Unified Ingestion & Embedding (Daily)"
        A1[Gmail API / OAuth2] -->|Download .xlsx| A2[gmail_adapter.py]
        A2 -->|Canonicalize & Redact| B1[ExcelProcessor]
        B1 -->|Trigger| D1[RagFlow Ingestion Pipeline]
        D1 -->|Layout Analysis| D2[Embedder: sentence-transformers]
        
        %% Unified DB Storage
        D2 -->|pgvector Upsert| DB[(PostgreSQL + pgvector)]
        B1 -->|SQL Table / Parquet| DB
    end

    subgraph "2. Hybrid Intent Parsing Engine"
        U[User Prompt] -->|POST /chat| API[FastAPI Orchestrator]
        API --> IP_LOCAL[Stage 1: Local spaCy Parser]
        
        %% Conditional Logic
        IP_LOCAL -->|Confidence < Threshold| IP_LLM[Stage 2: OpenAI Fallback Parser]
        IP_LOCAL -->|High Confidence| CM[ColumnMapper]
        IP_LLM -->|Structured JSON| CM
        
        CM -->|Fuzzy Resolve| QB[Structured Query Builder]
        QB -->|JSON Schema Check| VS[Validator]
    end

    subgraph "3. Deterministic vs. Semantic Execution"
        VS --> PLAN{Query Planner}
        
        %% Unified Querying
        PLAN -->|Quantitative| EXEC[Safe SQL Executor]
        PLAN -->|Qualitative| RAG[pgvector Retriever]
        
        EXEC -->|Query| DB
        RAG -->|Similarity Search| DB
        
        EXEC -->|Numeric Result| RES[Result Set]
        RAG -->|Context Fragments| EVI[Evidence Context]
    end

    subgraph "4. Multi-Provider Composer"
        RES & EVI --> COMP[Composer: LLM Adapter]
        COMP -->|Final Answer + Provenance| OUT[Response Metadata]
        
        subgraph "AI Providers"
            COMP --- P1[OpenAI / Bedrock]
            COMP --- P2[Local: Ollama]
        end
    end

    %% Highlighting
    style IP_LLM fill:#fff4dd,stroke:#d4a017,stroke-width:2px
    style DB fill:#336791,color:#fff,stroke-width:2px