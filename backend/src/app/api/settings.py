"""Admin settings API router for Phase 2.

Endpoints for viewing and updating application settings at runtime without restarting.
All /admin/settings endpoints require admin JWT role claim.
"""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
import structlog

from app.schemas.settings import (
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
    SettingMasked,
)
from app.services.settings_service import SettingsService
from app.auth import verify_admin

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/admin/settings", response_model=SettingsResponse, tags=["admin-settings"])
async def get_settings(admin=Depends(verify_admin)) -> SettingsResponse:
    """Retrieve all application settings.

    **Required**: Admin role (JWT with role='admin')

    **Response**: All settings with secrets masked, plus cache TTL info

    Secrets (marked is_secret=true) are returned as '***' to prevent exposure in logs or UIs.

    ---

    Example:
    ```bash
    curl http://localhost:8000/api/v1/admin/settings \\
      -H "Authorization: Bearer <admin_token>"

    # Response:
    {
      "items": [
        {
          "key": "ORCHESTRATOR_MODEL",
          "value": "gpt-4",
          "is_secret": false,
          "updated_at": "2024-01-15T10:30:00Z"
        },
        {
          "key": "OPENAI_API_KEY",
          "value": "***",
          "is_secret": true,
          "updated_at": "2024-01-15T09:00:00Z"
        }
      ],
      "cache_ttl_seconds": 60,
      "updated_at": "2024-01-15T10:30:00Z"
    }
    ```
    """
    try:
        settings_service = SettingsService()
        all_settings = await settings_service.get_all_settings()

        # Mask secrets in response
        items = []
        for setting in all_settings:
            if setting.get("is_secret"):
                value = "***"
            else:
                value = setting.get("value", "")

            items.append(
                SettingMasked(
                    key=setting.get("key", ""),
                    value=value,
                    is_secret=setting.get("is_secret", False),
                    updated_at=setting.get("updated_at"),
                )
            )

        logger.info("Retrieved all settings", count=len(items))

        return SettingsResponse(
            items=items,
            cache_ttl_seconds=60,
        )

    except Exception as exc:
        logger.error("Failed to retrieve settings", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings",
        ) from exc


@router.put("/admin/settings", response_model=SettingsUpdateResponse, tags=["admin-settings"])
async def update_settings(
    request: SettingsUpdateRequest,
    admin=Depends(verify_admin),
) -> SettingsUpdateResponse:
    """Batch create/update application settings.

    **Required**: Admin role (JWT with role='admin')

    **Request**: List of settings to create or update (key, value, is_secret flag)

    **Response**: Count updated, cache invalidation status

    After this endpoint completes:
    - Settings are written to the database (encrypted if is_secret=true)
    - Redis cache is immediately invalidated (key: setting:{key})
    - On next agent invocation, agents call settings_service.get_effective_provider_config() to read fresh values

    ---

    Example:
    ```bash
    curl -X PUT http://localhost:8000/api/v1/admin/settings \\
      -H "Authorization: Bearer <admin_token>" \\
      -H "Content-Type: application/json" \\
      -d '{
        "items": [
          {"key": "ORCHESTRATOR_MODEL", "value": "gpt-4o", "is_secret": false},
          {"key": "OPENAI_API_KEY", "value": "sk-...", "is_secret": true}
        ]
      }'

    # Response:
    {
      "updated_count": 2,
      "invalidated_cache": true,
      "message": "Settings updated successfully; changes take effect on next agent invocation"
    }
    ```
    """
    if not request.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No settings provided",
        )

    try:
        settings_service = SettingsService()
        updated_count = 0

        for item in request.items:
            # Validate key format (alphanumeric, underscore, hyphen)
            if not all(c.isalnum() or c in "_-" for c in item.key):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid setting key: {item.key}. Use alphanumeric, underscore, or hyphen only.",
                )

            # Store setting (with encryption if is_secret)
            await settings_service.set_setting(
                key=item.key,
                value=item.value,
                is_secret=item.is_secret,
            )
            updated_count += 1

            logger.info(
                "Setting updated",
                key=item.key,
                is_secret=item.is_secret,
            )

        logger.info("Settings batch update completed", updated_count=updated_count)

        return SettingsUpdateResponse(
            updated_count=updated_count,
            invalidated_cache=True,
        )

    except Exception as exc:
        logger.error("Failed to update settings", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings",
        ) from exc
