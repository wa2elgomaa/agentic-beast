"""Shared SQLAlchemy-backed session helpers for Agent SDK runs."""

from typing import Any, Mapping

from agents.extensions.memory import SQLAlchemySession

from app.config import settings
from app.db.session import engine


def _safe_segment(value: Any, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        return fallback
    return text.replace(" ", "_")


def build_agent_session_id(agent_name: str, context: Mapping[str, Any] | None = None) -> str:
    """Build a stable session key for an agent run."""
    ctx = context or {}
    explicit = ctx.get("agent_session_id")
    if explicit:
        return _safe_segment(explicit, "default")

    conversation_id = _safe_segment(ctx.get("conversation_id"), "no_conversation")
    raw_user_id = ctx.get("user_id")
    if raw_user_id is None or str(raw_user_id).strip() == "":
        raise ValueError("Authenticated user_id is required for agent sessions")

    user_id = _safe_segment(raw_user_id, "anonymous")
    agent = _safe_segment(agent_name, "agent")
    return f"agent:{agent}:conversation:{conversation_id}:user:{user_id}"


def get_agent_sqlalchemy_session(
    agent_name: str,
    context: Mapping[str, Any] | None = None,
) -> Any:
    """Create agent session for Runner.run, optionally encrypted."""
    session_id = build_agent_session_id(agent_name=agent_name, context=context)
    underlying = SQLAlchemySession(
        session_id,
        engine=engine,
        create_tables=True,
    )

    encryption_key = settings.agent_session_encryption_key.strip()
    if not encryption_key:
        return underlying

    # Lazy import keeps startup resilient when encryption extra is not installed.
    from agents.extensions.memory import EncryptedSession  # noqa: PLC0415

    return EncryptedSession(
        session_id=session_id,
        underlying_session=underlying,
        encryption_key=encryption_key,
        ttl=settings.agent_session_ttl_seconds,
    )
