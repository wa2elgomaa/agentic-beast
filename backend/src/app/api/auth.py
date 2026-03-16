"""Authentication utility endpoints (password reset)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.auth import ForgotPasswordRequest, MessageResponse, ResetPasswordRequest
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_user_service(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserService:
    return UserService(db)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    service: Annotated[UserService, Depends(get_user_service)],
):
    await service.create_reset_token(payload.email)
    return MessageResponse(message="If the email exists, a password reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    service: Annotated[UserService, Depends(get_user_service)],
):
    success = await service.reset_password_with_token(token=payload.token, new_password=payload.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    return MessageResponse(message="Password has been reset successfully")


@router.get("/validate-reset-token/{token}", response_model=MessageResponse)
async def validate_reset_token(
    token: str,
    service: Annotated[UserService, Depends(get_user_service)],
):
    is_valid = await service.validate_reset_token(token)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    return MessageResponse(message="Token is valid")
