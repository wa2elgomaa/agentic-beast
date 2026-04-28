"""Document Q&A Agent — answers questions about company documents using RAG.

Uses document_tools to retrieve relevant chunks from the documents table and
generates grounded answers with source citations.

Pattern: Real Strands ``Agent`` with document_tools registered.

Exported:
- ``DocumentAgentSchema``   — response schema
- ``DocumentAgent.execute`` — async entry point
- ``build_document_agent``  — constructs a configured Strands ``Agent``
- ``get_agent``             — factory helper
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel as PydanticBaseModel, Field
from strands import Agent

from app.config import settings
from app.logging import get_logger
from app.providers.factory import ProviderFactory

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class DocumentCitation(PydanticBaseModel):
    """A source citation from the retrieved document chunks."""
    source: str = Field(description="Document filename or title")
    page: Optional[int] = Field(default=None, description="Page number")
    chunk: Optional[int] = Field(default=None, description="Chunk index")


class DocumentAgentSchema(PydanticBaseModel):
    """Structured response from the document Q&A agent."""
    response_text: str = Field(description="Answer to the user's question with citations")
    citations: List[DocumentCitation] = Field(
        default_factory=list,
        description="Source citations supporting the answer",
    )


DOCUMENT_AGENT_SYSTEM_PROMPT = """\
You are a Company Document Q&A Agent. Your role is to answer questions about
internal company documents that have been uploaded to the system.

Your process:
1. Use search_documents to find the most relevant document chunks for the user's question.
2. Use format_citations to get structured source citations from the search results.
3. Synthesize an accurate, grounded answer using ONLY the retrieved document content.
4. Include source citations at the end of your response.

Rules:
- Base your answer exclusively on the retrieved documents. Do not use general knowledge.
- If no relevant documents are found, clearly state that you couldn't find relevant information.
- Always cite your sources using the format: "Source: [filename], page [N]".
- Keep the response concise and directly responsive to the question.
"""


def build_document_agent(model: Any) -> Agent:
    """Return a Strands Agent configured for document Q&A."""
    from app.tools.document_tools import format_citations, search_documents  # local import

    return Agent(
        model=model,
        system_prompt=DOCUMENT_AGENT_SYSTEM_PROMPT,
        tools=[search_documents, format_citations],
        callback_handler=None,
        structured_output_model=DocumentAgentSchema,
    )


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class DocumentAgent:
    """Answers questions about company documents using RAG."""

    def __init__(self) -> None:
        try:
            a = settings.main_agent
            self._agent_settings = a
        except Exception:
            from app.config import AISettings
            self._agent_settings = AISettings()
        self._factory = ProviderFactory(self._agent_settings)

    async def execute(self, context: Optional[Dict[str, Any]] = None) -> DocumentAgentSchema:
        """Run the document Q&A agent and return a grounded answer."""
        import asyncio

        if context is None:
            context = {}
        message: str = context.get("message") or ""

        model = self._factory.get_model(settings=self._agent_settings)
        agent = build_document_agent(model)

        try:
            result = await asyncio.to_thread(agent, message)
            structured: Optional[DocumentAgentSchema] = getattr(result, "structured_output", None)

            if structured is not None:
                return structured
            else:
                return DocumentAgentSchema(response_text=str(result))

        except Exception as exc:
            logger.error("Document agent error: %s", exc, exc_info=True)
            return DocumentAgentSchema(
                response_text="I encountered an error while searching documents. Please try again."
            )


def get_agent() -> DocumentAgent:
    """Return a new DocumentAgent instance."""
    return DocumentAgent()
