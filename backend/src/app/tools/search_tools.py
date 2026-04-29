"""
Google Custom Search Engine (CSE) tools for searching thenationalnews.com.

Implements rate-limit guarding with Redis for CSE quota management.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

import httpx
from redis.asyncio import Redis

from app.config import settings
from app.db.redis_session import get_redis

logger = logging.getLogger(__name__)


class CSESearchResult:
    """Data class representing a single search result."""

    def __init__(self, title: str, link: str, snippet: str):
        self.title = title
        self.link = link
        self.snippet = snippet

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "link": self.link,
            "snippet": self.snippet,
        }


class QuotaExceededError(Exception):
    """Raised when CSE daily quota is exceeded."""

    pass


class CSEError(Exception):
    """Raised when CSE API returns an error."""

    pass


async def _get_cse_daily_quota_key() -> str:
    """Get the Redis key for today's CSE request count."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return f"cse:daily:{today}"


async def _track_cse_request(redis: Redis) -> None:
    """
    Track a CSE request in Redis.

    Increments daily counter and sets TTL to end of day.
    Raises QuotaExceededError if within 10% of daily limit.
    """
    key = await _get_cse_daily_quota_key()
    limit = settings.google_cse_daily_limit
    warning_threshold = int(limit * 0.9)  # Warn at 90% (within 10%)

    # Increment counter
    current_count = await redis.incr(key)

    # Set TTL to end of day if first increment
    if current_count == 1:
        end_of_day = datetime.utcnow().replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        ttl_seconds = int((end_of_day - datetime.utcnow()).total_seconds())
        await redis.expire(key, ttl_seconds)

    # Check if approaching quota
    if current_count > limit:
        logger.warning(
            f"CSE quota exceeded: {current_count}/{limit} requests today"
        )
        raise QuotaExceededError(
            f"Google CSE daily limit ({limit}) reached. Please try again tomorrow."
        )

    if current_count >= warning_threshold:
        logger.warning(
            f"CSE quota warning: {current_count}/{limit} requests ({100 * current_count // limit}%)"
        )


async def search_tnn(
    query: str,
    num_results: int = 5,
) -> List[Dict[str, str]]:
    """
    Search thenationalnews.com using Google Custom Search Engine.

    Args:
        query: Search query string
        num_results: Number of results to return (max 10 per API call)

    Returns:
        List of search results with title, link, snippet

    Raises:
        QuotaExceededError: When daily quota is exceeded
        CSEError: When API returns an error
    """
    if not settings.google_cse_api_key or not settings.google_cse_id:
        raise CSEError(
            "Google CSE configuration missing. "
            "Please set GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID environment variables."
        )

    # Get Redis connection for quota tracking
    redis = await get_redis()

    # Track request and check quota
    try:
        await _track_cse_request(redis)
    except QuotaExceededError:
        raise

    # Build CSE API request URL
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.google_cse_api_key,
        "cx": settings.google_cse_id,
        "siteSearch": settings.google_cse_site,
        "q": query,
        "num": min(num_results, 10),  # API max is 10 per call
    }

    logger.info(f"Searching CSE for: {query} (results: {num_results})")

    # Make async HTTP request with timeout
    async with httpx.AsyncClient(timeout=settings.external_api_timeout_seconds) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"CSE API error: {e.response.status_code} - {e.response.text}")

            # Handle API-specific errors
            if e.response.status_code == 429:
                raise CSEError(
                    "Google CSE rate limit exceeded. Please try again later."
                )
            elif e.response.status_code == 403:
                raise CSEError("Google CSE API key or site restriction error.")
            elif e.response.status_code == 400:
                error_body = e.response.json()
                error_msg = error_body.get("error", {}).get("message", "Invalid request")
                raise CSEError(f"CSE API error: {error_msg}")
            else:
                raise CSEError(f"CSE API error: {e.response.status_code}")
        except httpx.TimeoutException:
            raise CSEError("Google CSE API request timed out.")
        except Exception as e:
            logger.error(f"Unexpected error calling CSE API: {str(e)}")
            raise CSEError(f"Unexpected CSE error: {str(e)}")

    # Parse response
    data = response.json()

    # Check for API errors in response
    if "error" in data:
        error = data["error"]
        error_msg = error.get("message", "Unknown error")
        logger.error(f"CSE API returned error: {error_msg}")
        raise CSEError(f"CSE error: {error_msg}")

    # Extract search results
    results = []
    items = data.get("items", [])

    for item in items:
        result = CSESearchResult(
            title=item.get("title", ""),
            link=item.get("link", ""),
            snippet=item.get("snippet", ""),
        )
        results.append(result.to_dict())

    logger.info(f"CSE returned {len(results)} results for: {query}")

    return results


# Export for tool registration
__all__ = ["search_tnn", "CSESearchResult", "QuotaExceededError", "CSEError"]
