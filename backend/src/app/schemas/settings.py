"""Pydantic schemas for admin settings API.

Settings can be updated at runtime via the API and are cached in Redis for performance.
Sensitive settings (marked as_secret=true) are encrypted with Fernet in the database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class SettingItem(BaseModel):
    """A single application setting (key-value pair)."""

    key: str = Field(
        description="Setting key (e.g., 'ORCHESTRATOR_MODEL', 'OPENAI_API_KEY')",
        min_length=1,
        max_length=255,
    )
    value: str = Field(
        description="Setting value (plaintext for non-secret settings, encrypted for secrets)",
        max_length=4096,
    )
    is_secret: bool = Field(
        default=False,
        description="If true, value is encrypted with Fernet in the database",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last update",
    )


class SettingsUpdateRequest(BaseModel):
    """Request body for batch updating settings."""

    items: list[SettingItem] = Field(
        description="List of settings to create/update",
        min_items=1,
        max_items=100,
    )


class SettingMasked(BaseModel):
    """A setting with secrets masked in API responses."""

    key: str
    value: str = Field(description="Masked value if is_secret=true (e.g., '***'), plaintext otherwise")
    is_secret: bool
    updated_at: Optional[datetime] = None


class SettingsResponse(BaseModel):
    """Response for GET /admin/settings."""

    items: list[SettingMasked] = Field(
        description="List of all application settings (if is_secret=true, value is masked with '***')"
    )
    cache_ttl_seconds: int = Field(
        default=60,
        description="Redis cache TTL; callers should assume maximum staleness of this duration",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last settings update",
    )


class SettingsUpdateResponse(BaseModel):
    """Response for PUT /admin/settings."""

    updated_count: int = Field(
        description="Number of settings updated/created"
    )
    invalidated_cache: bool = Field(
        default=True,
        description="Whether Redis cache was invalidated",
    )
    message: str = Field(
        default="Settings updated successfully; changes take effect on next agent invocation",
        description="Status message",
    )
