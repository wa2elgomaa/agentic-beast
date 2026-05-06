"""Conversation history utilities shared across agents."""

from __future__ import annotations

from typing import Any, Dict, List


def history_to_strands_messages(
    history: List[Dict[str, Any]],
    max_turns: int = 20,
) -> List[Dict[str, Any]]:
    """Convert conversation_history dicts to Strands ``messages=`` format.

    Takes the most recent *max_turns* entries and converts each
    ``{role, content}`` dict to ``{role, content: [{"text": ...}]}``.

    Migrated from ``analytics_agent._history_to_messages()``.
    """
    recent = history[-max_turns:] if max_turns and len(history) > max_turns else history
    messages: List[Dict[str, Any]] = []
    for turn in recent:
        role = turn.get("role", "user")
        if content := str(turn.get("content", "")).strip():
            messages.append({"role": role, "content": [{"text": content}]})
    return messages


def format_history_snippet(
    history: List[Dict[str, Any]],
    max_turns: int = 4,
) -> str:
    """Return a plain-text block of the last *max_turns* conversation turns.

    Used by ``ClassifyAgent`` for prompt injection only.
    Migrated from the inline history-formatting logic in ``classify_agent.py``.
    """
    if not history:
        return ""
    recent = history[-max_turns:]
    lines: List[str] = []
    for turn in recent:
        role = turn.get("role", "user")
        content = str(turn.get("content", "")).strip()[:200]
        lines.append(f"{role.capitalize()}: {content}")
    return "\n".join(lines)
