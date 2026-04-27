"""User management and authentication endpoints."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.users import (
    PasswordChange,
    TokenResponse,
    UserCreate,
    UserListResponse,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from app.services.auth_service import get_auth_service
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")


def get_user_service(db: Annotated[AsyncSession, Depends(get_db_session)]) -> UserService:
    return UserService(db)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    service: Annotated[UserService, Depends(get_user_service)],
):
    auth_service = get_auth_service()
    payload = auth_service.verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await service.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive or missing user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_admin(current_user=Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
):
    user = await service.create_user(payload)
    auth_service = get_auth_service()
    access_token = auth_service.create_access_token(user_id=str(user.id), username=user.username)
    return TokenResponse(access_token=access_token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    service: Annotated[UserService, Depends(get_user_service)],
):
    provider = payload.provider.lower()
    if provider in {"ldap", "ad", "active_directory"}:
        user = await service.authenticate_ldap(payload.username, payload.password)
    else:
        user = await service.authenticate_local(payload.username, payload.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = get_auth_service()
    access_token = auth_service.create_access_token(user_id=str(user.id), username=user.username)
    return TokenResponse(access_token=access_token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(current_user=Depends(get_current_user)):
    """Issue a fresh JWT for an already-authenticated user.

    The client should call this before the current token expires to maintain
    a seamless session without forcing a re-login.
    """
    auth_service = get_auth_service()
    access_token = auth_service.create_access_token(
        user_id=str(current_user.id), username=current_user.username
    )
    return TokenResponse(access_token=access_token, user=UserResponse.model_validate(current_user))


@router.get("", response_model=UserListResponse)
async def list_users(
    service: Annotated[UserService, Depends(get_user_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    _admin=Depends(get_current_admin),
):
    return await service.list_users(page=page, page_size=page_size, is_active=is_active)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    service: Annotated[UserService, Depends(get_user_service)],
    _admin=Depends(get_current_admin),
):
    user = await service.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    service: Annotated[UserService, Depends(get_user_service)],
    _admin=Depends(get_current_admin),
):
    user = await service.update_user(user_id, payload)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.post("/change-password")
async def change_password(
    payload: PasswordChange,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user=Depends(get_current_user),
):
    success = await service.change_password(
        user_id=str(current_user.id),
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid current password")
    return {"message": "Password changed successfully"}


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str,
    service: Annotated[UserService, Depends(get_user_service)],
    _admin=Depends(get_current_admin),
):
    success = await service.deactivate_user(user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"message": "User deactivated successfully"}
