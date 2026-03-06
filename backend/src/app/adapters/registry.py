"""Adapter registry for discovering and managing data adapters."""

from typing import Dict, Optional, Type

from app.adapters.base import DataAdapter
from app.logging import get_logger

logger = get_logger(__name__)


class AdapterRegistry:
    """Registry for managing pluggable data adapters."""

    def __init__(self):
        """Initialize the registry."""
        self._adapters: Dict[str, Type[DataAdapter]] = {}
        self._instances: Dict[str, DataAdapter] = {}

    def register(self, name: str, adapter_class: Type[DataAdapter]) -> None:
        """Register an adapter class.

        Args:
            name: Unique identifier for the adapter.
            adapter_class: The adapter class to register.
        """
        if name in self._adapters:
            logger.warning("Adapter already registered", adapter_name=name)
        self._adapters[name] = adapter_class
        logger.info("Adapter registered", adapter_name=name, adapter_class=adapter_class.__name__)

    def get_adapter(self, name: str) -> Optional[DataAdapter]:
        """Get an adapter instance by name.

        Args:
            name: The adapter identifier.

        Returns:
            The adapter instance, or None if not found.
        """
        if name not in self._adapters:
            logger.warning("Adapter not found", adapter_name=name)
            return None

        # Return cached instance if available
        if name in self._instances:
            return self._instances[name]

        # Create new instance
        adapter_class = self._adapters[name]
        instance = adapter_class(name)
        self._instances[name] = instance
        logger.info("Adapter instance created", adapter_name=name)
        return instance

    def discover_adapters(self) -> Dict[str, str]:
        """Discover all registered adapters.

        Returns:
            Dictionary mapping adapter names to their class names.
        """
        return {name: cls.__name__ for name, cls in self._adapters.items()}

    def unregister(self, name: str) -> None:
        """Unregister an adapter.

        Args:
            name: The adapter identifier.
        """
        if name in self._adapters:
            del self._adapters[name]
            if name in self._instances:
                del self._instances[name]
            logger.info("Adapter unregistered", adapter_name=name)


# Global registry instance
_registry = AdapterRegistry()


def get_registry() -> AdapterRegistry:
    """Get the global adapter registry."""
    return _registry


def register_adapter(name: str, adapter_class: Type[DataAdapter]) -> None:
    """Register an adapter with the global registry."""
    _registry.register(name, adapter_class)


def get_adapter(name: str) -> Optional[DataAdapter]:
    """Get an adapter from the global registry."""
    return _registry.get_adapter(name)


def discover_adapters() -> Dict[str, str]:
    """Discover all registered adapters."""
    return _registry.discover_adapters()
