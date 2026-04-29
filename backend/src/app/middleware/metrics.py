"""Prometheus metrics middleware."""
import time
from typing import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

# Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)

DATABASE_OPERATIONS = Counter(
    "database_operations_total",
    "Total database operations",
    ["operation_type", "table"]
)

AI_PROVIDER_REQUESTS = Counter(
    "ai_provider_requests_total", 
    "Total AI provider requests",
    ["provider", "model", "status"]
)

AI_PROVIDER_DURATION = Histogram(
    "ai_provider_request_duration_seconds",
    "AI provider request duration in seconds",
    ["provider", "model"]
)

DOCUMENT_UPLOADS = Counter(
    "document_uploads_total",
    "Total document uploads",
    ["status"]
)

CHAT_MESSAGES = Counter(
    "chat_messages_total",
    "Total chat messages processed",
    ["agent_type"]
)

# ── Phase 2 metrics (T115) ──────────────────────────────────────────────────

SEARCH_REQUESTS_TOTAL = Counter(
    "search_requests_total",
    "Total Google CSE search requests",
    ["status"],  # success | quota_exceeded | error
)

ARTICLE_VECTORS_COUNT = Counter(
    "article_vectors_count",
    "Total article_vectors rows written (cumulative ingestion count)",
)

TAG_VECTORS_COUNT = Counter(
    "tag_vectors_count",
    "Total tag embedding operations performed",
)

WEBHOOK_EVENTS_TOTAL = Counter(
    "webhook_events_total",
    "Total webhook events received",
    ["source", "event_type"],
)

SETTINGS_CACHE_HIT_RATIO = Counter(
    "settings_cache_hits_total",
    "Total settings lookups served from Redis cache (use with settings_cache_misses_total for ratio)",
)

SETTINGS_CACHE_MISS_TOTAL = Counter(
    "settings_cache_misses_total",
    "Total settings lookups that missed Redis cache and hit the database",
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics collection for the metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)
            
        start_time = time.time()
        
        # Extract endpoint pattern for better labeling
        endpoint = self._get_endpoint_pattern(request)
        
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception as e:
            # Count errors as 500s
            status_code = "500"
            # Re-raise the exception to let other middleware handle it
            raise e
        finally:
            # Record metrics
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()
            
            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=endpoint
            ).observe(time.time() - start_time)
        
        return response
    
    def _get_endpoint_pattern(self, request: Request) -> str:
        """Extract endpoint pattern from request."""
        path = request.url.path
        
        # Common patterns to normalize
        patterns = [
            ("/api/v1/documents/", "/api/v1/documents/{id}"),
            ("/api/v1/chat/conversations/", "/api/v1/chat/conversations/{id}"),
            ("/api/v1/users/", "/api/v1/users/{id}"),
            ("/api/v1/analytics/", "/api/v1/analytics/{query}"),
        ]
        
        for prefix, pattern in patterns:
            if path.startswith(prefix) and len(path) > len(prefix):
                return pattern
                
        return path


def get_metrics() -> StarletteResponse:
    """Return Prometheus metrics in the expected format."""
    return StarletteResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )