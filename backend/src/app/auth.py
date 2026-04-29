"""Authentication dependency aliases.

Re-exports admin authentication dependencies so API modules can import
from a single ``app.auth`` namespace rather than the API layer directly.
"""

from app.api.users import get_current_admin as verify_admin  # noqa: F401

__all__ = ["verify_admin"]
