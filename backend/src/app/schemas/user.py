"""SQLAlchemy model for the users table."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import uuid

from .document import Base


class User(Base):
    """Users table model."""
    
    __tablename__ = "users"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User credentials 
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255))  # Nullable for AD users
    
    # User status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Authentication
    auth_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="local")  # 'local' or 'active_directory'
    ad_username: Mapped[Optional[str]] = mapped_column(String(255))  # ActiveDirectory username if different
    
    # Activity tracking
    last_login: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __repr__(self) -> str:
        """String representation."""
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
