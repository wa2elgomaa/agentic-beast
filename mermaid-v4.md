graph TD
    %% ─────────────────────────────────────────────────────────────
    %% Phase 2 Architecture  ★ = new in Phase 2
    %% ─────────────────────────────────────────────────────────────

    %% Global Class Definitions
    classDef user      fill:#1a73e8,color:#fff,stroke:none
    classDef api       fill:#0f9d58,color:#fff,stroke:none
    classDef agent     fill:#7b2fff,color:#fff,stroke:none
    classDef store     fill:#34495e,color:#fff,stroke:none
    classDef queue     fill:#c0392b,color:#fff,stroke:none
    classDef ingest    fill:#16a085,color:#fff,stroke:none
    classDef decision  fill:#e37400,color:#fff,stroke:none
    classDef newnode   fill:#b03a2e,color:#fff,stroke:#ff8a80,stroke-width:2px
    classDef ui        fill:#2471a3,color:#fff,stroke:none

    %% ── External & Entry Points ──────────────────────────────────
    USER(["User / Client App"]):::user
    ADMIN(["Admin UI"]):::user
    CELERY_BEAT(["Celery Beat"]):::user
    GMAIL_API(["Gmail API\nOAuth2 PKCE"]):::ingest
    EXT_SYS(["External Systems ★\n(Webhook Push)"]):::newnode

    %% ── Frontend UI Layer ★ ──────────────────────────────────────
    subgraph UI_LAYER["Frontend (Next.js) ★"]
        CHAT_UI["Chat UI"]:::ui
        TOOL_SEL["Tool Selector ★\n(+ icon: Search · Documents)"]:::newnode
    end

    %% ── FastAPI Layer ────────────────────────────────────────────
    subgraph HTTP_GATEWAY["FastAPI Layer"]
        API_CHAT["POST /chat\n(JWT Auth)"]:::api
        API_WS["WS /ws/voice"]:::api
        API_INGESTION["POST /admin/ingestion\n(Gmail Trigger)"]:::api
        API_WEBHOOK["POST /ingest/webhook ★\n(External Push · HMAC)"]:::newnode
        API_DATASETS["POST /admin/datasets ★\n(Doc Upload)"]:::newnode
        API_TAGS["GET|POST|DELETE ★\n/admin/tags"]:::newnode
        API_SETTINGS["GET|PUT ★\n/admin/settings"]:::newnode
    end

    %% ── Admin Board ★ ────────────────────────────────────────────
    subgraph ADMIN_BOARD["Admin Board ★"]
        direction LR
        SET_DASH["Settings Dashboard ★\n(Model Providers · API Keys)"]:::newnode
        DS_DASH["Datasets Dashboard ★\n(Upload · Browse · Delete)"]:::newnode
        TAG_DASH["Tags Dashboard ★\n(CRUD · CSV Bulk Upload)"]:::newnode
        ING_DASH["Ingestion Dashboard\n(Gmail · Webhook · Folder)"]:::api
    end

    %% ── Chat & AI Orchestration ──────────────────────────────────
    subgraph ORCHESTRATION["Chat & AI Orchestration"]
        direction TB
        CHAT_SVC["Chat Service\nHistory & DB Persistence"]:::api
        CTX_DEC{"Shortcut?"}:::decision
        ORCH_AGENT["Orchestrator Agent\n(gpt-4o-mini)\nReads runtime config ★"]:::agent

        subgraph SUB_AGENTS["Strands Sub-Agents"]
            direction LR
            ANA_AGENT["Analytics Agent\n(Gemma 4 / E2B)"]:::agent
            CHAT_AGENT["Chat Agent\n(Gemma 4 / E2B)\n+ Doc RAG"]:::agent
            VOICE_AGENT["Voice Agent\n(Whisper-1)"]:::agent
            TAG_AGENT["Tagging Agent ★\n(Gemma 4)\nTag Vector Enhanced"]:::newnode
            REC_AGENT["Recommendation Agent ★\n(Gemma 4)\nArticle Vector Enhanced"]:::newnode
            DOC_AGENT["Document Agent ★\n(Gemma 4)\nRAG + Citations"]:::newnode
            SEARCH_AGENT["Search Agent ★\n(Gemma 4)\nCSE Tool"]:::newnode
        end
    end

    %% ── Agent Tools ──────────────────────────────────────────────
    subgraph TOOLS["Agent Tools"]
        SQL_TOOL["SQL Database Tool\n(Read-only)"]:::api
        DOC_VEC["Document Vector Search\n(pgvector)"]:::api
        ART_VEC["Article Vector Search ★\n(pgvector)"]:::newnode
        TAG_VEC["Tag Vector Search ★\n(pgvector)"]:::newnode
        CSE_TOOL["Google CSE Tool ★\nthenationalnews.com scoped"]:::newnode
    end

    %% ── Asynchronous Ingestion Pipeline ─────────────────────────
    subgraph INGESTION_PIPE["Asynchronous Ingestion Pipeline"]
        direction TB
        REDIS_Q[("Redis Broker\nCelery Queue")]:::queue

        subgraph GMAIL_PIPE["Gmail Pipeline"]
            direction TB
            CELERY_P["Parent Task\n(List Emails)"]:::queue
            CELERY_C["Child Task\n(Single Email)"]:::queue
            GADP["Gmail Adapter\n(Cursor-paged)"]:::ingest
            subgraph PROCESSING["Data Processing & Upsert"]
                direction TB
                EXTRACT["Extract & Parse\n(Excel/HTTP)"]:::ingest
                SMAP["Schema Mapper"]:::ingest
                DEDUP_LOGIC{"Deduplication\nLogic"}:::decision
                P1["P1: Identifier Hash"]:::ingest
                P2["P2: Connection Hash"]:::ingest
                P3["P3: Legacy Row Ref"]:::ingest
            end
            MR["Mark as Read\n(Success Only)"]:::ingest
        end

        subgraph FOLDER_PIPE["Folder Watcher Pipeline ★"]
            direction TB
            FW_TASK["Periodic Celery Task\n(Beat Schedule)"]:::queue
            FW_SCAN["Scan watched_documents/\n(Redis Dedup)"]:::ingest
            FW_PROC["Extract & Chunk\n(PDF/Excel/Text)"]:::ingest
            FW_EMBED["Embed Chunks\n(384-dim) → pgvector"]:::newnode
        end

        subgraph UPLOAD_PIPE["Manual Upload Pipeline ★"]
            direction TB
            UP_RECV["Upload Receiver"]:::ingest
            S3_STORE["S3 Upload ★\n(Document Storage)"]:::newnode
            UP_PROC["Extract & Chunk"]:::ingest
            UP_EMBED["Embed & Upsert ★\n(pgvector)"]:::newnode
        end

        subgraph WEBHOOK_PIPE["Webhook Ingestion ★"]
            direction TB
            WH_RECV["Webhook Receiver ★\n(HMAC Verified)"]:::newnode
            WH_ROUTE{"Route by\nSource ★"}:::decision
            WH_ART["Article Upsert ★\n+ Re-Vectorize"]:::newnode
            WH_GEN["Generic Data ★\nUpsert"]:::newnode
        end

        subgraph ARTICLE_PIPE["CMS Article Pipeline ★"]
            direction TB
            ART_SCRAPE["Article Scraper ★\n(Initial Bulk Load)"]:::newnode
            ART_CHUNK["Chunk & Embed ★\n(384-dim)"]:::newnode
            ART_UPSERT["Upsert article_vectors ★\n(pgvector)"]:::newnode
        end
    end

    %% ── Persistence Layer ────────────────────────────────────────
    subgraph STORES["Persistence Layer"]
        DB[(PostgreSQL\nMain DB)]:::store
        VEC_DOC[("Doc Vectors\n(pgvector 384-dim)")]:::store
        VEC_ART[("Article Vectors ★\n(pgvector 384-dim)")]:::newnode
        VEC_TAG[("Tag Vectors ★\n(pgvector 384-dim)")]:::newnode
        S3[("S3 Bucket ★\nDocument Storage")]:::newnode
        CONV[("Conversation Logs")]:::store
        CFG_DB[("App Settings ★\nDB-persisted Config")]:::newnode
    end

    %% ── Relationships ────────────────────────────────────────────

    %% UI / Entry
    USER --> CHAT_UI
    CHAT_UI --> TOOL_SEL
    CHAT_UI -->|HTTPS| API_CHAT
    CHAT_UI -->|WebSocket| API_WS
    EXT_SYS -->|HMAC-signed POST| API_WEBHOOK

    %% Admin Board routing
    ADMIN --> ADMIN_BOARD
    SET_DASH <-->|Read/Write| API_SETTINGS
    DS_DASH <-->|Manage| API_DATASETS
    TAG_DASH <-->|CRUD| API_TAGS
    ING_DASH --> API_INGESTION
    API_SETTINGS -->|Persist| CFG_DB

    %% Chat Flow
    API_CHAT --> CHAT_SVC
    API_WS --> VOICE_AGENT
    CHAT_SVC --> CTX_DEC
    CTX_DEC -->|Yes - Shortcut| CHAT_SVC
    CTX_DEC -->|No| ORCH_AGENT
    ORCH_AGENT -->|Read runtime config| CFG_DB

    ORCH_AGENT -->|Tool Call| ANA_AGENT
    ORCH_AGENT -->|Tool Call| CHAT_AGENT
    ORCH_AGENT -->|Tool Call| TAG_AGENT
    ORCH_AGENT -->|Tool Call| REC_AGENT
    ORCH_AGENT -->|Tool Call| DOC_AGENT
    ORCH_AGENT -->|Tool Call| SEARCH_AGENT

    TOOL_SEL -->|Activates| SEARCH_AGENT
    TOOL_SEL -->|Activates| DOC_AGENT

    ANA_AGENT --> SQL_TOOL
    CHAT_AGENT --> DOC_VEC
    TAG_AGENT --> TAG_VEC
    REC_AGENT --> ART_VEC
    DOC_AGENT --> DOC_VEC
    SEARCH_AGENT --> CSE_TOOL

    SQL_TOOL -->|SELECT| DB
    DOC_VEC -->|Similarity Search| VEC_DOC
    ART_VEC -->|Similarity Search| VEC_ART
    TAG_VEC -->|Similarity Search| VEC_TAG
    CHAT_SVC -->|Persist History| CONV

    %% Gmail Ingestion Flow
    API_INGESTION --> REDIS_Q
    REDIS_Q --> CELERY_P
    CELERY_P --> GMAIL_API
    GMAIL_API --> GADP
    GADP --> CELERY_C
    CELERY_C --> EXTRACT --> SMAP --> DEDUP_LOGIC
    DEDUP_LOGIC --> P1 & P2 & P3
    P1 & P2 & P3 -->|Upsert| DB
    DB --> MR

    %% Folder Watcher Flow
    CELERY_BEAT --> FW_TASK
    FW_TASK --> FW_SCAN --> FW_PROC --> FW_EMBED -->|Upsert| VEC_DOC

    %% Manual Upload Flow
    API_DATASETS --> UP_RECV
    UP_RECV --> S3_STORE & UP_PROC
    S3_STORE --> S3
    UP_PROC --> UP_EMBED -->|Upsert| VEC_DOC

    %% Webhook Flow
    API_WEBHOOK --> WH_RECV --> WH_ROUTE
    WH_ROUTE -->|Article event| WH_ART -->|Re-vectorize| VEC_ART
    WH_ROUTE -->|Generic event| WH_GEN -->|Upsert| DB

    %% Article Scraper / Vectorization
    ART_SCRAPE --> ART_CHUNK --> ART_UPSERT --> VEC_ART

    %% Tags vectorization (admin-triggered via Tags Dashboard) ★
    TAG_DASH -->|Trigger re-embed| VEC_TAG
    API_TAGS -->|CRUD| DB

    %% Shared Storage Links
    VEC_DOC --- DB
    VEC_ART --- DB
    VEC_TAG --- DB