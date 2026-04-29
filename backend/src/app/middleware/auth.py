"""Authentication middleware.

Pre-authorize incoming requests using either an API key (x-api-key) or a
JWT bearer token. When a valid credential is found the middleware sets
`request.state.user` so downstream handlers and dependencies can access
the authenticated user. This middleware intentionally keeps logic simple
and defers full user resolution to `UserService` when an API key maps to
a configured user id.

This file provides a lightweight place to later add refresh-token
handling and token introspection.
"""

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED

from app.config import settings
from app.logging import get_logger
from app.services.auth_service import get_auth_service
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService

logger = get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that pre-authorizes requests.

    Behavior:
    - If `x-api-key` header matches `settings.api_key` we consider the
      request authenticated. If `settings.api_key_user_id` is set the
      middleware will resolve that user from the database and attach it
      to `request.state.user`.
    - If `Authorization: Bearer <token>` is provided we verify the JWT
      using `AuthService.verify_token()` and attach the payload to
      `request.state.user` when valid.
    - For protected routes (API endpoints) if no valid credential is
      present the middleware returns `401 Unauthorized`.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path or ""

        # Allow public endpoints and docs without auth
        if (
            path.startswith("/swagger")
            or path.startswith("/redoc")
            or path.startswith("/api/openapi.json")
            or path.startswith("/health")
            or path.startswith("/metrics")
        ):
            return await call_next(request)

        # Prefer API key if present
        x_api_key = request.headers.get("x-api-key")
        if x_api_key:
            if settings.api_key and x_api_key == settings.api_key:
                # Optionally resolve a mapped user id to a real user
                if settings.api_key_user_id:
                    try:
                        async with AsyncSessionLocal() as session:
                            user = await UserService(session).get_user_by_id(settings.api_key_user_id)
                            request.state.user = user
                    except Exception as e:  # pragma: no cover - defensive logging
                        logger.warning("Failed to resolve API key user id", error=str(e))
                else:
                    request.state.user = {"id": "api_key", "username": "service"}
                return await call_next(request)

        # Fall back to bearer token (JWT)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            payload = get_auth_service().verify_token(token)
            if payload:
                request.state.user = payload
                return await call_next(request)
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=HTTP_401_UNAUTHORIZED)

        # Enforce authentication on API/chat routes
        if path.startswith("/api") or path.startswith("/chat") or path.startswith("/ws"):
            return JSONResponse({"detail": "Authentication required"}, status_code=HTTP_401_UNAUTHORIZED)

        # Non-protected route, continue
        return await call_next(request)


def get_auth_middleware():
    """Return the middleware class so callers can conditionally add it.

    Example in `main.create_app()`:
        app.add_middleware(AuthMiddleware)
    """

    return AuthMiddleware
