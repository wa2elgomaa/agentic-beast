"""Sentry configuration and integration."""
import logging
import os
from typing import Optional

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from app.config import settings

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize Sentry SDK with FastAPI integration."""
    if not settings.sentry_dsn:
        logger.info("Sentry DSN not configured, skipping Sentry initialization")
        return
        
    try:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            release=settings.api_version,
            
            # Performance monitoring
            traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
            profiles_sample_rate=0.1,  # 10% for profiling
            
            # Error handling
            attach_stacktrace=True,
            send_default_pii=False,  # Don't send PII data
            
            # Integrations
            integrations=[
                FastApiIntegration(auto_enabling=True),
                SqlalchemyIntegration(),
                AsyncioIntegration(),
                RedisIntegration(),
                LoggingIntegration(
                    level=logging.INFO,        # Capture info and above as breadcrumbs
                    event_level=logging.ERROR  # Send errors and above as events
                ),
            ],
            
            # Additional options
            max_breadcrumbs=50,
            before_send=before_send_filter,
        )
        
        logger.info(f"Sentry initialized for environment: {settings.environment}")
        
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")


def before_send_filter(event, hint):
    """Filter events before sending to Sentry."""
    
    # Don't send health check errors
    if "exception" in event:
        exc_info = hint.get("exc_info")
        if exc_info:
            exception = exc_info[1]
            if hasattr(exception, "__str__") and "health" in str(exception).lower():
                return None
    
    # Don't send certain HTTP errors
    if "request" in event:
        url = event.get("request", {}).get("url", "")
        if "/health" in url or "/metrics" in url:
            return None
            
    return event


def capture_exception(error: Exception, extra: Optional[dict] = None) -> None:
    """Capture exception with additional context."""
    with sentry_sdk.push_scope() as scope:
        if extra:
            for key, value in extra.items():
                scope.set_tag(key, value)
        
        sentry_sdk.capture_exception(error)


def capture_message(message: str, level: str = "info", extra: Optional[dict] = None) -> None:
    """Capture custom message."""
    with sentry_sdk.push_scope() as scope:
        if extra:
            for key, value in extra.items():
                scope.set_tag(key, value)
                
        sentry_sdk.capture_message(message, level)


def set_user_context(user_id: str, email: Optional[str] = None) -> None:
    """Set user context for error tracking."""
    with sentry_sdk.configure_scope() as scope:
        scope.set_user({
            "id": user_id,
            "email": email
        })


def set_request_context(request_id: str, endpoint: str, method: str) -> None:
    """Set request context for error tracking."""
    with sentry_sdk.configure_scope() as scope:
        scope.set_tag("request_id", request_id)
        scope.set_tag("endpoint", endpoint)
        scope.set_tag("method", method)