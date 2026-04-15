"""User management service."""

import secrets
import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.schemas.users import UserCreate, UserListResponse, UserResponse, UserUpdate
from app.services.auth_service import get_auth_service
from app.services.email_service import get_email_service
from app.utils import utc_now


class UserService:
    """Service for user creation, auth, and lifecycle operations."""

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.auth_service = get_auth_service()
        self.email_service = get_email_service()

    async def _flush_and_refresh_user(self, user: User) -> User:
        """Ensure server-managed fields are loaded before ORM serialization."""
        await self.db_session.flush()
        await self.db_session.refresh(user)
        return user

    async def create_user(self, user_data: UserCreate) -> User:
        query = select(User).where(
            or_(User.username == user_data.username, User.email == user_data.email)
        )
        result = await self.db_session.execute(query)
        if result.scalar_one_or_none() is not None:
            raise ValueError("Username or email already exists")

        user = User(
            id=uuid.uuid4(),
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=self.auth_service.get_password_hash(user_data.password),
            is_admin=user_data.is_admin,
            is_active=True,
            auth_provider="local",
        )
        self.db_session.add(user)
        return await self._flush_and_refresh_user(user)

    async def authenticate_local(self, username: str, password: str) -> Optional[User]:
        user = await self.get_user_by_username(username)
        if not user or not user.is_active:
            return None
        if user.auth_provider != "local" or not user.hashed_password:
            return None

        if not self.auth_service.verify_password(password, user.hashed_password):
            return None

        user.last_login = utc_now()
        self.db_session.add(user)
        return await self._flush_and_refresh_user(user)

    async def authenticate_ldap(self, username: str, password: str) -> Optional[User]:
        ldap_user = await self.auth_service.authenticate_ldap(username, password)
        if not ldap_user:
            return None

        user = await self.get_user_by_username(username)
        if user is None:
            user = User(
                id=uuid.uuid4(),
                username=username,
                email=f"{username}@ldap.local",
                full_name=username,
                hashed_password=None,
                is_admin=False,
                is_active=True,
                auth_provider="active_directory",
                ad_username=username,
                last_login=utc_now(),
            )
            self.db_session.add(user)
        else:
            user.last_login = utc_now()
            user.auth_provider = "active_directory"
            self.db_session.add(user)

        return await self._flush_and_refresh_user(user)

    async def get_user_by_id(self, user_id: str | uuid.UUID) -> Optional[User]:
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
        result = await self.db_session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        result = await self.db_session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.db_session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_users(self, page: int = 1, page_size: int = 20, is_active: Optional[bool] = None) -> UserListResponse:
        offset = (page - 1) * page_size

        query = select(User)
        count_query = select(func.count(User.id))
        if is_active is not None:
            query = query.where(User.is_active == is_active)
            count_query = count_query.where(User.is_active == is_active)

        query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)

        total_result = await self.db_session.execute(count_query)
        total = total_result.scalar() or 0

        users_result = await self.db_session.execute(query)
        users = users_result.scalars().all()

        return UserListResponse(
            users=[UserResponse.model_validate(user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(users) < total,
        )

    async def update_user(self, user_id: str, user_data: UserUpdate) -> Optional[User]:
        user = await self.get_user_by_id(user_id)
        if not user:
            return None

        if user_data.email is not None:
            user.email = user_data.email
        if user_data.full_name is not None:
            user.full_name = user_data.full_name
        if user_data.is_active is not None:
            user.is_active = user_data.is_active
        if user_data.is_admin is not None:
            user.is_admin = user_data.is_admin

        self.db_session.add(user)
        return await self._flush_and_refresh_user(user)

    async def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        user = await self.get_user_by_id(user_id)
        if not user or user.auth_provider != "local" or not user.hashed_password:
            return False

        if not self.auth_service.verify_password(current_password, user.hashed_password):
            return False

        user.hashed_password = self.auth_service.get_password_hash(new_password)
        self.db_session.add(user)
        await self.db_session.flush()
        return True

    async def reset_password(self, user_id: uuid.UUID, new_password: str) -> bool:
        user = await self.get_user_by_id(user_id)
        if not user:
            return False

        user.hashed_password = self.auth_service.get_password_hash(new_password)
        user.auth_provider = "local"
        self.db_session.add(user)
        await self.db_session.flush()
        return True

    async def deactivate_user(self, user_id: str) -> bool:
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        user.is_active = False
        self.db_session.add(user)
        await self.db_session.flush()
        return True

    async def create_reset_token(self, email: str) -> bool:
        """Issue a password reset token and send reset email if user exists."""
        user = await self.get_user_by_email(email)
        if user is None:
            # Avoid leaking whether an email exists.
            return True

        token = secrets.token_urlsafe(48)
        expires_at = utc_now() + timedelta(minutes=settings.password_reset_token_ttl_minutes)

        self.db_session.add(
            PasswordResetToken(
                user_id=user.id,
                token=token,
                expires_at=expires_at,
            )
        )
        await self.db_session.flush()

        return await self.email_service.send_password_reset_email(
            to_email=user.email,
            reset_token=token,
            username=user.username,
        )

    async def validate_reset_token(self, token: str) -> bool:
        """Check whether a reset token exists and has not expired."""
        query = select(PasswordResetToken).where(
            PasswordResetToken.token == token,
            PasswordResetToken.expires_at > utc_now(),
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none() is not None

    async def reset_password_with_token(self, token: str, new_password: str) -> bool:
        """Consume reset token and update password in one transaction."""
        query = select(PasswordResetToken).where(
            PasswordResetToken.token == token,
            PasswordResetToken.expires_at > utc_now(),
        )
        result = await self.db_session.execute(query)
        reset_token = result.scalar_one_or_none()
        if reset_token is None:
            return False

        changed = await self.reset_password(reset_token.user_id, new_password)
        if not changed:
            return False

        await self.db_session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.token == token)
        )
        await self.db_session.flush()
        return True
