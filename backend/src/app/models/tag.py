"""SQLAlchemy model for the tags table."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from .document import Base


class Tag(Base):
    """Tags table model."""
    
    __tablename__ = "tags"

    # Primary key
    slug: Mapped[str] = mapped_column(String, primary_key=True)
    
    # Tag information
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    variations: Mapped[Optional[List]] = mapped_column(JSONB)  # Array of string variations/synonyms
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Vector embedding for semantic matching
    embedding: Mapped[Optional[list]] = mapped_column(Vector(384))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __repr__(self) -> str:
        """String representation."""
        return f"<Tag(slug='{self.slug}', name='{self.name}', is_primary={self.is_primary})>"