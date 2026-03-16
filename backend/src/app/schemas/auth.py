"""Authentication and password reset schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator


def _ensure_bcrypt_byte_limit(password: str) -> str:
    """Validate bcrypt 72-byte input limit using UTF-8 byte length."""
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or fewer when UTF-8 encoded")
    return password


class ForgotPasswordRequest(BaseModel):
    """Forgot-password request payload."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Password reset payload."""

    token: str = Field(..., min_length=20)
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_byte_length(cls, value: str) -> str:
        return _ensure_bcrypt_byte_limit(value)


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
