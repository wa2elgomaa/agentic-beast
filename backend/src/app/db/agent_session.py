"""Session ID helpers for agent runs."""

from typing import Any, Mapping


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
    # Allow anonymous sessions when no authenticated user_id is present.
    # Previously this raised ValueError which bubbled up and was treated as a
    # classification failure by the orchestrator. Using an anonymous fallback
    # avoids converting unrelated runtime issues into "classification_error".
    user_id = _safe_segment(raw_user_id, "anonymous")
    agent = _safe_segment(agent_name, "agent")
    return f"agent:{agent}:conversation:{conversation_id}:user:{user_id}"
