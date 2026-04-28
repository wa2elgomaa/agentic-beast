"""Document retrieval tools for company document Q&A (RAG pipeline).

Provides:
- search_documents: vector similarity search in the documents table
- format_citations: extract structured source citations from chunks
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from strands import tool

_logger = logging.getLogger(__name__)

# Metadata key that marks a row as a company document chunk
_DOC_SOURCE_TYPE = "company_document"


@tool
async def search_documents(query: str, top_k: int = 5) -> str:
    """Search company document chunks using semantic similarity.

    Embeds the query, then performs a pgvector cosine similarity search
    restricted to rows where doc_metadata->>'source_type' = 'company_document'.

    Args:
        query: The user's question or search query.
        top_k: Number of most relevant chunks to return (default 5, max 20).

    Returns:
        JSON string with list of relevant chunks including text, source, page,
        chunk index, and similarity score.
    """
    top_k = min(top_k, 20)

    if not query or not query.strip():
        return json.dumps({"error": "query is required", "chunks": []})

    # 1. Embed the query
    try:
        from app.services.embedding_service import EmbeddingService

        embedding_svc = EmbeddingService()
        embedding = embedding_svc.embed_text(query[:2000])
    except Exception as exc:
        _logger.error("Embedding failed for query: %s", exc)
        return json.dumps({"error": f"Embedding failed: {exc}", "chunks": []})

    # 2. Vector similarity search in PostgreSQL
    try:
        from app.db.session import AsyncSessionLocal

        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT
                        id,
                        text,
                        doc_metadata,
                        1 - (embedding <=> :emb::vector) AS similarity_score
                    FROM documents
                    WHERE
                        embedding IS NOT NULL
                        AND doc_metadata->>'source_type' = :source_type
                    ORDER BY embedding <=> :emb::vector
                    LIMIT :limit
                    """
                ),
                {
                    "emb": embedding_str,
                    "source_type": _DOC_SOURCE_TYPE,
                    "limit": top_k,
                },
            )
            rows = result.fetchall()

        chunks = []
        for row in rows:
            meta: dict[str, Any] = row.doc_metadata or {}
            chunks.append({
                "id": row.id,
                "text": row.text,
                "source": meta.get("source", ""),
                "page": meta.get("page"),
                "chunk": meta.get("chunk"),
                "similarity_score": round(float(row.similarity_score or 0.0), 4),
            })

        return json.dumps({"chunks": chunks, "count": len(chunks), "query": query})

    except Exception as exc:
        _logger.error("Document search failed: %s", exc)
        return json.dumps({"error": str(exc), "chunks": []})


@tool
def format_citations(chunks_json: str) -> str:
    """Extract structured source citations from document search results.

    Args:
        chunks_json: JSON string output from search_documents (must include
            a "chunks" list with source, page, chunk fields).

    Returns:
        JSON string with a deduplicated list of citations and a formatted
        citation string suitable for inclusion in an LLM response.
    """
    try:
        data = json.loads(chunks_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid chunks_json: {exc}", "citations": []})

    if "error" in data:
        return chunks_json

    chunks: list[dict[str, Any]] = data.get("chunks", [])
    if not chunks:
        return json.dumps({"citations": [], "citation_text": "No sources found."})

    # Build deduplicated citations
    seen: set[str] = set()
    citations: list[dict[str, Any]] = []

    for chunk in chunks:
        source = chunk.get("source") or "Unknown document"
        page = chunk.get("page")
        citation_key = f"{source}:p{page}"
        if citation_key in seen:
            continue
        seen.add(citation_key)
        citations.append({
            "source": source,
            "page": page,
            "chunk": chunk.get("chunk"),
        })

    # Format as human-readable citation string
    parts = []
    for i, c in enumerate(citations, start=1):
        page_str = f", page {c['page']}" if c.get("page") else ""
        parts.append(f"[{i}] {c['source']}{page_str}")

    citation_text = "\n".join(parts) if parts else "No sources."

    return json.dumps({
        "citations": citations,
        "citation_text": citation_text,
    })
