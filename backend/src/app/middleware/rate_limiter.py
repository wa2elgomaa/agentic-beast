"""Simple rate limiter middleware.

This implements a fixed-window counter per client identifier (x-api-key, Authorization token, or client IP).
It's an in-memory, per-process limiter suitable for development and lightweight protection.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from fastapi import Request
from pydantic import BaseModel
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


class RateLimiterConfig(BaseModel):
    enabled: bool = settings.rate_limit_enabled
    calls: int = settings.rate_limit_calls
    period: int = settings.rate_limit_period


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Optional[RateLimiterConfig] = None):
        super().__init__(app)
        self.config = config or RateLimiterConfig()

    async def dispatch(self, request: Request, call_next):
        if not self.config.enabled:
            return await call_next(request)

        # Identify client: prefer API key header, then Authorization, then client IP
        identifier = request.headers.get("x-api-key")
        if not identifier:
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if auth:
                identifier = auth.split(" ", 1)[-1].strip()

        if not identifier:
            client = request.client
            identifier = client.host if client else "unknown"

        now = time.time()
        store = request.app.state.rate_limit_store
        locks = request.app.state.rate_limit_locks

        # Ensure a lock exists for this identifier
        lock = locks.get(identifier)
        if lock is None:
            lock = asyncio.Lock()
            locks[identifier] = lock

        async with lock:
            entry = store.get(identifier)
            if entry is None:
                # (count, window_start)
                store[identifier] = [1, now]
            else:
                count, window_start = entry
                if now - window_start >= self.config.period:
                    store[identifier] = [1, now]
                else:
                    if count + 1 > self.config.calls:
                        # Rate limit exceeded
                        retry_after = int(window_start + self.config.period - now) + 1
                        payload = {
                            "error": "rate_limited",
                            "message": "Too many requests, please retry later.",
                            "retry_after": retry_after,
                        }
                        logger.warning("Rate limit exceeded", identifier=identifier)
                        return JSONResponse(payload, status_code=429, headers={"Retry-After": str(retry_after)})
                    store[identifier][0] = count + 1

        return await call_next(request)
