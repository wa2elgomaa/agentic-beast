from typing import Optional

from fastapi import Header, Depends, HTTPException, status, Request

from app.api.users import get_user_service, get_current_user, oauth2_scheme
from app.config import settings
from app.services.user_service import UserService
from app.schemas.user import User


async def get_current_user_or_apikey(
    x_api_key: Optional[str] = Header(None),
    service: UserService = Depends(get_user_service),
):
    """Allow authentication via API key (x-api-key) or fall back to JWT.

    If `x-api-key` is provided and matches `settings.api_key`, the user
    specified by `settings.api_key_user_id` is returned (must exist).
    Otherwise the normal JWT-based `get_current_user` should be used by
    the caller as a fallback dependency.
    """
    if x_api_key:
        if settings.api_key and x_api_key == settings.api_key:
            if not settings.api_key_user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key user not configured")
            user = await service.get_user_by_id(settings.api_key_user_id)
            if user is None or not user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key user")
            return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    # No API key provided — caller should provide a separate JWT-based dependency.
    # We raise a special exception to indicate no API key was present so callers
    # can fall back to the JWT dependency if desired.
    raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="No API key provided")


async def get_authenticated_user(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    service: UserService = Depends(get_user_service),
):
    """Unified dependency: prefer API key auth, fall back to JWT via get_current_user.

    Note: `token` is provided via the same OAuth2 scheme the app uses. We call
    into `get_current_user` if no API key is present.
    """
    # If API key provided, validate and return mapped user
    if x_api_key:
        if settings.api_key and x_api_key == settings.api_key:
            if not settings.api_key_user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key user not configured")
            user = await service.get_user_by_id(settings.api_key_user_id)
            if user is None or not user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key user")
            return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    # No API key — first honor any test/runtime overrides of get_current_user
    try:
        from app.main import app as _fastapi_app
        override = getattr(_fastapi_app, "dependency_overrides", {}).get(get_current_user)
        if override:
            result = override()
            import asyncio
            if asyncio.iscoroutine(result):
                return await result
            return result
    except Exception:
        # ignore and continue to normal JWT path
        pass

    # Fall back to JWT-based get_current_user: extract Authorization Bearer token
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    actual_token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        actual_token = auth_header.split(" ", 1)[1].strip()

    return await get_current_user(actual_token, service)
