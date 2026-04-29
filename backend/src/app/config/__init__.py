"""Configuration and registry management for agentic-beast.

This package exposes a `Settings` class and a `settings` instance. For
historical reasons there are two configuration modules in the repo:
`app/config.py` (full feature set) and `app/config_settings.py` (lightweight
alternative). Prefer the authoritative `app/config.py` when available by
dynamically loading it; fall back to `app/config_settings` if needed.
"""

from app.config.config import (
    settings,
    Settings,
    AISettings
)
# Import registry classes
from app.config.registry import (
    SchemaRegistry,
    IntentRegistry,
    AgentSettingsRegistry,
    initialize_registries,
    get_schema_registry,
    get_intent_registry,
    get_agent_settings_registry,
)

__all__ = [
    "Settings",
    "settings",
    "AISettings",
    "SchemaRegistry",
    "IntentRegistry",
    "AgentSettingsRegistry",
    "initialize_registries",
    "get_schema_registry",
    "get_intent_registry",
    "get_agent_settings_registry",
]
