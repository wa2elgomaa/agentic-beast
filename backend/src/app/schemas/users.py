"""User and authentication schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


def _ensure_bcrypt_byte_limit(password: str) -> str:
    """Validate bcrypt 72-byte input limit using UTF-8 byte length."""
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or fewer when UTF-8 encoded")
    return password


class UserBase(BaseModel):
    """Base user fields."""

    username: str = Field(..., min_length=3, max_length=255)
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for user registration."""

    password: str = Field(..., min_length=8, max_length=255)
    is_admin: bool = False

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, value: str) -> str:
        return _ensure_bcrypt_byte_limit(value)
    

class UserUpdate(BaseModel):
    """Schema for user updates."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class UserLogin(BaseModel):
    """Schema for user login."""

    username: str
    password: str
    provider: str = Field(default="local", description="local or ldap")


class PasswordChange(BaseModel):
    """Schema for password change."""

    current_password: str
    new_password: str = Field(..., min_length=8, max_length=255)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_byte_length(cls, value: str) -> str:
        return _ensure_bcrypt_byte_limit(value)


class UserResponse(UserBase):
    """Public user response schema."""

    id: UUID
    is_active: bool
    is_admin: bool
    auth_provider: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str
    username: str
    exp: int


class TokenResponse(BaseModel):
    """Token response schema."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserListResponse(BaseModel):
    """Paginated user list."""

    users: list[UserResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
