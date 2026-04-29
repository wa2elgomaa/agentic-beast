"""Shim module to keep `app.services.chat_service` import path working.

The real implementation has moved to `app.services.v1.chat_service.ChatService`.
"""

from .v1.chat_service import ChatService

__all__ = ["ChatService"]
