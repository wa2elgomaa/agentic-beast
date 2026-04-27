"""SessionManager: coordinate limited runtime sessions with queue semantics.

This implementation is intentionally small but production-minded: it keeps
an in-memory registry of active sessions, supports a configurable maximum
concurrency, and offers simple queue policies: 'cancel_oldest', 'queue',
and 'reject'. It is not distributed — for multi-instance deployments a
central coordinator (Redis, DB, or etcd) is required.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SessionRecord:
    session_id: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


class SessionManager:
    """Manage runtime sessions with a small in-memory queue.

    This manager is safe for use within a single process. It exposes hooks
    for observability and supports preemption via `interrupt_session()`.
    """

    def __init__(self, max_concurrent: Optional[int] = None):
        self._max = max_concurrent or settings.max_sessions
        self._active: Dict[str, SessionRecord] = {}
        self._queue: List[SessionRecord] = []
        self._lock = asyncio.Lock()

    async def create_session(self, session_id: str, metadata: Optional[dict] = None, queue_policy: str = "cancel_oldest") -> SessionRecord:
        """Create or enqueue a session.

        queue_policy:
            - cancel_oldest: close the oldest active session to make room
            - queue: place the session into the pending queue
            - reject: raise RuntimeError when at capacity
        """
        async with self._lock:
            metadata = metadata or {}
            if session_id in self._active:
                logger.debug("Session already active", session_id=session_id)
                return self._active[session_id]

            if len(self._active) < self._max:
                rec = SessionRecord(session_id=session_id, metadata=metadata)
                self._active[session_id] = rec
                logger.info("Session created", session_id=session_id)
                return rec

            # At capacity
            if queue_policy == "cancel_oldest":
                # Remove oldest active session
                oldest_id = min(self._active.values(), key=lambda r: r.created_at).session_id
                await self.close_session(oldest_id)
                rec = SessionRecord(session_id=session_id, metadata=metadata)
                self._active[session_id] = rec
                logger.info("Replaced oldest session with new session", old=oldest_id, new=session_id)
                return rec

            if queue_policy == "queue":
                rec = SessionRecord(session_id=session_id, metadata=metadata)
                self._queue.append(rec)
                logger.info("Session queued", session_id=session_id, queue_len=len(self._queue))
                return rec

            # Reject
            raise RuntimeError("Maximum concurrent sessions reached")

    async def close_session(self, session_id: str) -> bool:
        """Close a session and promote next queued session if present.

        Returns True if the session existed and was removed.
        """
        async with self._lock:
            removed = False
            if session_id in self._active:
                del self._active[session_id]
                removed = True
                logger.info("Session closed", session_id=session_id)

            # Promote queued session if space
            if self._queue and len(self._active) < self._max:
                rec = self._queue.pop(0)
                self._active[rec.session_id] = rec
                logger.info("Promoted queued session", session_id=rec.session_id, queue_len=len(self._queue))

            return removed

    async def interrupt_session(self, session_id: str) -> bool:
        """Mark a session for interruption. For now this simply closes it.

        Real implementations should signal the runtime to gracefully interrupt.
        """
        logger.info("Interrupting session", session_id=session_id)
        return await self.close_session(session_id)

    async def list_active(self) -> List[SessionRecord]:
        async with self._lock:
            return list(self._active.values())

    async def get_session(self, session_id: str) -> Optional[SessionRecord]:
        async with self._lock:
            return self._active.get(session_id)


# Module-level singleton
_MANAGER: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SessionManager()
    return _MANAGER


__all__ = ["SessionManager", "get_session_manager"]
