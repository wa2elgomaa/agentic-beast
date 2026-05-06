"""Redis-backed per-conversation asset store.

Stores analytics artifacts (chart base64, caption, raw SQL rows, etc.) keyed
by conversation_id so concurrent requests never clobber each other.

All methods are synchronous so they can be called from both regular tool threads
(python_repl, db_tool) and async service code without event-loop conflicts.
Falls back gracefully if Redis is unavailable.
"""

from __future__ import annotations

import threading
from typing import Optional

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_TTL = 3600  # 1 hour — assets expire well after any single session


class ConversationAssetService:
    """Thread-safe Redis-backed store for per-conversation analytics assets.

    Uses a lazy-initialised singleton sync Redis client (``redis.Redis``) so it
    can be called from both async and sync contexts.  Falls back to a no-op if
    Redis is unavailable so the system degrades gracefully.

    Key layout (all expire after ``_DEFAULT_TTL`` seconds):
        conv_asset:{conv_id}:chart_b64       — base64-encoded PNG
        conv_asset:{conv_id}:chart_caption   — human-readable chart title
    """

    _client: Optional["redis.Redis"] = None  # type: ignore[name-defined]
    _init_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Internal: Redis client                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def _get_client(cls) -> Optional["redis.Redis"]:  # type: ignore[name-defined]
        """Return the singleton sync Redis client, initialising it on first call."""
        if cls._client is not None:
            return cls._client

        with cls._init_lock:
            if cls._client is not None:  # double-checked locking
                return cls._client
            try:
                import redis as _redis

                client = _redis.Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_timeout=2,
                    socket_connect_timeout=2,
                    max_connections=20,
                )
                client.ping()  # fail fast if Redis is down
                cls._client = client
                logger.info(
                    "ConversationAssetService: Redis connected at %s",
                    settings.redis_url,
                )
            except Exception as exc:
                logger.warning(
                    "ConversationAssetService: Redis unavailable (%s) — "
                    "falling back to in-memory global store",
                    exc,
                )
                # Leave cls._client as None so callers fall back to global store
        return cls._client

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def store_chart(
        cls,
        conversation_id: str,
        b64: str,
        caption: str,
        ttl: int = _DEFAULT_TTL,
    ) -> bool:
        """Persist a base64 PNG chart for *conversation_id*.

        Args:
            conversation_id: The conversation UUID string.
            b64:             Base64-encoded PNG data.
            caption:         Human-readable chart title.
            ttl:             Redis key TTL in seconds (default 1 hour).

        Returns:
            True on success, False if Redis is unavailable or an error occurred.
        """
        if not conversation_id or not b64:
            return False
        client = cls._get_client()
        if client is None:
            return False
        try:
            pipe = client.pipeline()
            pipe.setex(f"conv_asset:{conversation_id}:chart_b64", ttl, b64)
            pipe.setex(f"conv_asset:{conversation_id}:chart_caption", ttl, caption)
            pipe.execute()
            logger.debug(
                "ConversationAssetService: stored chart for conv %s (%d B64 chars)",
                conversation_id,
                len(b64),
            )
            return True
        except Exception as exc:
            logger.warning("ConversationAssetService.store_chart: %s", exc)
            return False

    @classmethod
    def pop_chart(cls, conversation_id: str) -> tuple[str, str]:
        """Return *and delete* the stored chart for *conversation_id*.

        This is an atomic get+delete (pipeline) so each chart is consumed
        exactly once regardless of concurrent callers.

        Returns:
            ``(chart_b64, chart_caption)`` — both empty strings if nothing stored.
        """
        if not conversation_id:
            return "", ""
        client = cls._get_client()
        if client is None:
            return "", ""
        try:
            b64_key = f"conv_asset:{conversation_id}:chart_b64"
            caption_key = f"conv_asset:{conversation_id}:chart_caption"
            pipe = client.pipeline()
            pipe.get(b64_key)
            pipe.get(caption_key)
            pipe.delete(b64_key, caption_key)
            results = pipe.execute()
            return results[0] or "", results[1] or ""
        except Exception as exc:
            logger.warning("ConversationAssetService.pop_chart: %s", exc)
            return "", ""

    @classmethod
    def clear(cls, conversation_id: str) -> None:
        """Delete all stored assets for *conversation_id*.

        Call this before each new agent invocation to prevent stale charts
        from a previous turn leaking into the current one.
        """
        if not conversation_id:
            return
        client = cls._get_client()
        if client is None:
            return
        try:
            client.delete(
                f"conv_asset:{conversation_id}:chart_b64",
                f"conv_asset:{conversation_id}:chart_caption",
            )
        except Exception as exc:
            logger.warning("ConversationAssetService.clear: %s", exc)
