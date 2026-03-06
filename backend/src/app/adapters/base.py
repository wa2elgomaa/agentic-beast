"""Abstract base class for pluggable data adapters."""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AdapterStatus(str, Enum):
    """Status of a data adapter."""

    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FETCHING = "fetching"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class AdapterHealthStatus(BaseModel):
    """Health status of a data adapter."""

    status: AdapterStatus
    last_fetch: Optional[datetime] = None
    error_message: Optional[str] = None
    records_processed: int = 0
    records_failed: int = 0


class DataAdapter(ABC):
    """Abstract base class for all data adapters."""

    def __init__(self, name: str):
        """Initialize the adapter."""
        self.name = name
        self.health_status = AdapterHealthStatus(status=AdapterStatus.DISCONNECTED)

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to data source."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to data source."""
        pass

    @abstractmethod
    async def fetch_data(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch data from the source.

        Returns:
            List of data records as dictionaries.
        """
        pass

    @abstractmethod
    async def get_status(self) -> AdapterHealthStatus:
        """Get adapter health status."""
        pass

    async def __aenter__(self):
        """Async context manager enter."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
