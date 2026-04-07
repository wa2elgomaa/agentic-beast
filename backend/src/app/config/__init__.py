"""Configuration and registry management for agentic-beast."""

# Import Settings from the renamed module
from app.config_settings import Settings, settings

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
    "SchemaRegistry",
    "IntentRegistry",
    "AgentSettingsRegistry",
    "initialize_registries",
    "get_schema_registry",
    "get_intent_registry",
    "get_agent_settings_registry",
]
