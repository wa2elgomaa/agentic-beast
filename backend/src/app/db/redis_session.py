"""Redis async client dependency.

Provides a reusable async Redis client for FastAPI dependencies and
background tasks.  The client is created lazily on first access and
reused across requests.
"""

from redis.asyncio import Redis

from app.config import settings

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Return a shared async Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client
