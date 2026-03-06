# Research: Agentic AI Assistant Platform

**Feature**: 001-agentic-ai-assistant
**Date**: 2026-03-05

## R1: Agentic Framework — Strands Agents SDK vs LangChain

**Decision**: Use AWS Strands Agents SDK as the primary agent framework, with LangChain used only for memory management and document processing utilities (text splitters, embeddings).

**Rationale**: Strands Agents SDK provides native AWS Bedrock integration, tool-use patterns that align with the structured query approach, and a simpler agent lifecycle model than LangChain's full agent executor. Using Strands for orchestration keeps the agent layer thin and focused while LangChain's mature document processing utilities (RecursiveCharacterTextSplitter, embedding integrations) remain useful for the RAG pipeline.

**Alternatives considered**:
- LangChain-only: More mature ecosystem but heavier abstraction layer; agent executor patterns are more complex than needed for tool-calling agents.
- CrewAI: Good for multi-agent workflows but adds another dependency layer; less native AWS integration.
- Custom agent loop: Maximum control but higher development effort; reinvents tool-calling patterns.

## R2: Hybrid Analytics Data Access Architecture

**Decision**: Four-layer hybrid approach:
1. **Structured Query Objects** (primary): Agent produces typed query parameters (metric, date_range, platform, group_by) that tool functions translate to safe parameterized SQL.
2. **Tool Functions** (execution): Pre-built functions like `get_metrics()`, `get_top_posts()`, `compare_platforms()` encapsulate query logic with whitelist validation.
3. **RAG / Vector Retrieval** (context): Embedded analytics records in `documents.embedding` support semantic search for contextual evidence and explanation.
4. **Pre-computed Summaries** (acceleration): Daily/weekly/monthly aggregates in a `summaries` table for common queries (total reach, top posts, platform comparison).

**Rationale**: Structured queries ensure safety (no raw SQL injection risk) while tool functions provide composability. RAG adds contextual depth the LLM needs for explanation. Pre-computed summaries avoid expensive aggregations on every request.

**Alternatives considered**:
- NL-to-SQL: Rejected by user — too risky and fragile for production.
- RAG-only: Insufficient for precise numerical aggregation; vector search doesn't reliably return exact sums/counts.
- Pre-computed-only: Too rigid; cannot handle ad-hoc questions not covered by pre-defined aggregations.

## R3: Gmail API Integration Pattern

**Decision**: Use Google Gmail API with OAuth2 service account for server-to-server access. Celery periodic task polls the inbox on a configurable interval (default: every 5 minutes). Processed emails are marked with a Gmail label to prevent re-processing.

**Rationale**: Polling with label-based tracking is simpler and more reliable than Gmail push notifications (which require a public webhook endpoint). The service account approach avoids interactive OAuth flows for a backend service.

**Alternatives considered**:
- Gmail push notifications (Pub/Sub): Requires a public endpoint and Google Cloud Pub/Sub setup; overkill for local-first development.
- IMAP polling: Simpler but deprecated by Google for most use cases; less reliable metadata access.
- Microsoft Graph (Outlook): Not applicable; user specified Gmail.

## R4: Embedding Model Selection

**Decision**: Use `all-MiniLM-L6-v2` (384-dimension) for all embeddings — analytics records, tags, and company documents. Run locally via `sentence-transformers` library.

**Rationale**: Content is primarily English (Arabic best-effort). MiniLM-L6-v2 provides good quality-to-speed ratio for 384-dim vectors, compatible with the existing `vector(384)` schema in `init.sql`. Running locally avoids API costs and latency for embedding generation.

**Alternatives considered**:
- OpenAI text-embedding-3-small: Higher quality but adds API dependency and cost; conflicts with local-first development goal.
- multilingual-e5-base: Better Arabic support but larger model (768-dim) requiring schema change; unnecessary given "primarily English" clarification.
- BGE-small-en: Similar quality to MiniLM but less community adoption.

## R5: Document Processing Pipeline

**Decision**: Use LangChain's `RecursiveCharacterTextSplitter` for document chunking. PDF extraction via `PyPDF2`, image OCR via `pytesseract` (optional, deferred if complex), Excel via `openpyxl`, plain text directly. Chunks stored in `documents` table with embeddings.

**Rationale**: LangChain's text splitters handle overlapping chunks and respect document structure. PyPDF2 is lightweight and sufficient for text-based PDFs. Image OCR can be deferred to a later phase if not immediately needed.

**Alternatives considered**:
- Unstructured.io: More powerful document parsing but heavy dependency; overkill for initial scope.
- LlamaParse: Cloud-based; conflicts with local-first requirement.
- Custom chunking: Unnecessary when LangChain text splitters are well-tested.

## R6: CMS API Integration

**Decision**: Implement a CMS API client as a tool function in `tools/cms_tools.py`. Single-article fetch via CMS REST API with HTTP client (httpx async). For bulk similarity search in article recommendations, query MongoDB directly using `motor` (async MongoDB driver).

**Rationale**: The CMS API provides the canonical article representation for tag suggestion. Direct MongoDB access is needed for bulk similarity search across the article corpus where the CMS API would be too slow (N+1 queries). This dual-access pattern was confirmed in clarifications.

**Alternatives considered**:
- CMS API only: Too slow for bulk similarity search; would require pagination and multiple round-trips.
- MongoDB only: Would bypass CMS business logic and validation; article schema might differ from CMS canonical format.

## R7: Authentication Strategy

**Decision**: JWT-based authentication with two providers: local (username/password with bcrypt hashing) and Active Directory (LDAP bind). JWT tokens issued on login, validated on each API request via FastAPI dependency injection.

**Rationale**: Existing `users` table already has `auth_provider` field supporting 'local' and 'active_directory'. JWT is stateless and well-suited for API-only architecture. LDAP bind for AD is the simplest integration pattern.

**Alternatives considered**:
- Session-based auth: Requires server-side session storage; adds complexity for API-only service.
- OAuth2 with external IdP: Over-engineered for an internal tool.

## R8: Pre-computed Summary Strategy

**Decision**: Create a `summaries` table with materialized aggregations at daily, weekly, and monthly granularity. A Celery task recomputes summaries after each successful data ingestion. Summaries cover: total reach, total impressions, total interactions, engagement rate, top posts by metric, and platform comparisons.

**Rationale**: Common analytics queries (weekly/monthly totals, platform comparisons) are expensive to compute on-the-fly from raw records. Pre-computing after ingestion amortizes the cost and enables sub-second responses for the most frequent queries.

**Alternatives considered**:
- PostgreSQL materialized views: Simpler but less flexible for different granularities; harder to control refresh timing.
- Redis cache: Fast but loses data on restart; not suitable for aggregations that need persistence.
- On-demand only: Too slow for large date ranges; SC-001 requires <10s for 1 year of data.
