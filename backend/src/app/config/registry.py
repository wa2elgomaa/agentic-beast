"""
Configuration registries for autonomous agents.

Loads YAML schemas and dynamically provides:
- SchemaRegistry: Metrics, dimensions, column mappings
- IntentRegistry: Intent taxonomy, classification rules
- AgentSettingsRegistry: Timeouts, limits, model parameters
"""

import json
from pathlib import Path
from typing import Any, Optional
import yaml
from functools import lru_cache

from app.logging import get_logger

logger = get_logger(__name__)


class SchemaRegistry:
    """Load and query social media analytics schema from YAML."""

    def __init__(self, yaml_path: str | Path):
        """Initialize schema registry from YAML file."""
        self.path = Path(yaml_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Schema registry file not found: {yaml_path}")
        
        with open(self.path) as f:
            self.data = yaml.safe_load(f)
        
        self.schema = self.data.get("schema", {})
        logger.info("SchemaRegistry initialized", path=str(self.path))

    @property
    def table_name(self) -> str:
        """Get the main table name."""
        return self.schema.get("table", "documents")

    @property
    def metrics(self) -> dict[str, dict]:
        """Get all metrics definitions."""
        return self.schema.get("metrics", {})

    @property
    def dimensions(self) -> dict[str, dict]:
        """Get all dimensions definitions."""
        return self.schema.get("dimensions", {})

    @property
    def numeric_defaults(self) -> list[str]:
        """Get fields that default to 0 when NULL."""
        return self.schema.get("numeric_defaults", [])

    @property
    def fingerprint_metrics(self) -> list[str]:
        """Get metrics used for duplicate detection fingerprints."""
        return self.schema.get("fingerprint_metrics", [])

    @property
    def constraints(self) -> dict:
        """Get query constraints."""
        return self.schema.get("constraints", {})

    def get_metric_aliases(self, metric_name: str) -> list[str]:
        """Get all aliases for a metric (including the metric name itself)."""
        m = self.metrics.get(metric_name, {})
        return [metric_name] + m.get("aliases", [])

    def resolve_metric(self, user_term: str) -> Optional[str]:
        """
        Find canonical metric name from user-facing term.
        
        Args:
            user_term: User's term (e.g., "views", "total reach", "engagements")
        
        Returns:
            Canonical metric name (e.g., "video_views", "total_reach") or None
        """
        term_lower = user_term.lower().strip()
        
        # Direct match first
        if term_lower in self.metrics:
            return term_lower
        
        # Search aliases
        for metric_name, config in self.metrics.items():
            aliases = [alias.lower() for alias in self.get_metric_aliases(metric_name)]
            if term_lower in aliases:
                return metric_name
        
        return None

    def get_dimension_aliases(self, dimension_name: str) -> list[str]:
        """Get all aliases for a dimension."""
        d = self.dimensions.get(dimension_name, {})
        return [dimension_name] + d.get("aliases", [])

    def resolve_dimension(self, user_term: str) -> Optional[str]:
        """
        Find canonical dimension name from user-facing term.
        
        Args:
            user_term: User's term (e.g., "platform", "date", "social platform")
        
        Returns:
            Canonical dimension name or None
        """
        term_lower = user_term.lower().strip()
        
        # Direct match first
        if term_lower in self.dimensions:
            return term_lower
        
        # Search aliases
        for dim_name, config in self.dimensions.items():
            aliases = [alias.lower() for alias in self.get_dimension_aliases(dim_name)]
            if term_lower in aliases:
                return dim_name
        
        return None

    def get_metric_mapping(self) -> dict[str, str]:
        """
        Build exhaustive alias → canonical metric name mapping.
        
        Used by NLP layer for column resolution.
        
        Returns:
            Dict: {alias: canonical_name}
        """
        mapping = {}
        for metric_name, config in self.metrics.items():
            # Add canonical name
            mapping[metric_name] = metric_name
            # Add all aliases
            for alias in config.get("aliases", []):
                mapping[alias] = metric_name
        return mapping

    def get_dimension_mapping(self) -> dict[str, str]:
        """Build exhaustive alias → canonical dimension mapping."""
        mapping = {}
        for dim_name, config in self.dimensions.items():
            mapping[dim_name] = dim_name
            for alias in config.get("aliases", []):
                mapping[alias] = dim_name
        return mapping

    def get_valid_metrics(self) -> set[str]:
        """Get set of all valid canonical metric names."""
        return set(self.metrics.keys())

    def get_valid_dimensions(self) -> set[str]:
        """Get set of all valid canonical dimension names."""
        return set(self.dimensions.keys())

    def get_aggregations_for_metric(self, metric_name: str) -> list[str]:
        """Get allowed aggregation functions for a metric."""
        m = self.metrics.get(metric_name, {})
        return m.get("aggregations", ["sum"])


class IntentRegistry:
    """Load and query intent taxonomy from YAML."""

    def __init__(self, yaml_path: str | Path):
        """Initialize intent registry from YAML file."""
        self.path = Path(yaml_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Intent registry file not found: {yaml_path}")
        
        with open(self.path) as f:
            self.data = yaml.safe_load(f)
        
        logger.info("IntentRegistry initialized", path=str(self.path))

    @property
    def intents(self) -> dict[str, dict]:
        """Get all intent definitions."""
        return self.data.get("intents", {})

    @property
    def classification_settings(self) -> dict:
        """Get intent classification settings."""
        return self.data.get("classification_settings", {})

    @property
    def routing_rules(self) -> dict:
        """Get intent routing rules."""
        return self.data.get("routing_rules", {})

    @property
    def valid_intents(self) -> list[str]:
        """Get list of valid intent names."""
        return list(self.intents.keys())

    @property
    def fallback_intent(self) -> str:
        """Get fallback intent when classification fails."""
        return self.classification_settings.get("fallback_intent", "general")

    @property
    def confidence_threshold(self) -> float:
        """Get minimum confidence threshold for intent classification."""
        return self.classification_settings.get("confidence_threshold", 0.7)

    def get_intent_aliases(self, intent_name: str) -> list[str]:
        """Get all aliases for an intent."""
        i = self.intents.get(intent_name, {})
        return [intent_name] + i.get("aliases", [])

    def resolve_intent(self, user_term: str) -> Optional[str]:
        """
        Find canonical intent name from user-facing term.
        
        Args:
            user_term: User's term or intent name
        
        Returns:
            Canonical intent name or None
        """
        term_lower = user_term.lower().strip()
        
        # Direct match
        if term_lower in self.intents:
            return term_lower
        
        # Search aliases
        for intent_name, config in self.intents.items():
            aliases = [alias.lower() for alias in self.get_intent_aliases(intent_name)]
            if term_lower in aliases:
                return intent_name
        
        return None

    def get_intent_description(self, intent_name: str) -> str:
        """Get description for an intent."""
        i = self.intents.get(intent_name, {})
        return i.get("description", "")

    def get_intent_example_queries(self, intent_name: str) -> list[str]:
        """Get example queries for an intent."""
        i = self.intents.get(intent_name, {})
        return i.get("examples", [])

    def get_routing_for_intent(self, intent_name: str) -> dict:
        """Get routing rules for an intent."""
        return self.routing_rules.get(intent_name, {})


class AgentSettingsRegistry:
    """Load and query agent settings from YAML."""

    def __init__(self, yaml_path: str | Path):
        """Initialize agent settings registry from YAML file."""
        self.path = Path(yaml_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Agent settings file not found: {yaml_path}")
        
        with open(self.path) as f:
            self.data = yaml.safe_load(f)
        
        logger.info("AgentSettingsRegistry initialized", path=str(self.path))

    @property
    def agents(self) -> dict[str, dict]:
        """Get all agent configurations."""
        return self.data.get("agents", {})

    @property
    def code_interpreter(self) -> dict:
        """Get code interpreter settings."""
        return self.data.get("code_interpreter", {})

    @property
    def database(self) -> dict:
        """Get database settings."""
        return self.data.get("database", {})

    @property
    def value_guard(self) -> dict:
        """Get value guard settings."""
        return self.data.get("value_guard", {})

    @property
    def retry_policy(self) -> dict:
        """Get retry policy settings."""
        return self.data.get("retry_policy", {})

    def get_agent_config(self, agent_name: str) -> dict:
        """Get configuration for a specific agent."""
        return self.agents.get(agent_name, {})

    def get_agent_timeout(self, agent_name: str) -> float:
        """Get LLM timeout for an agent (seconds)."""
        agent = self.agents.get(agent_name, {})
        return agent.get("lm_timeout_seconds", 30.0)

    def get_agent_model(self, agent_name: str) -> str:
        """Get default LLM model for an agent."""
        agent = self.agents.get(agent_name, {})
        return agent.get("model", "gpt-4o-mini")

    def get_agent_temperature(self, agent_name: str) -> float:
        """Get LLM temperature for an agent."""
        agent = self.agents.get(agent_name, {})
        return agent.get("temperature", 0.1)

    def get_database_timeout(self) -> int:
        """Get database statement timeout (ms)."""
        return self.database.get("statement_timeout_ms", 10000)

    def get_max_rows_per_query(self) -> int:
        """Get maximum rows per query."""
        return self.database.get("max_rows_per_query", 200)

    def get_code_interpreter_timeout(self) -> int:
        """Get code interpreter sandbox timeout (seconds)."""
        return self.code_interpreter.get("timeout_seconds", 30)

    def get_value_guard_threshold(self) -> int:
        """Get value guard validation threshold."""
        return self.value_guard.get("threshold", 100)


# Global singleton registries - loaded at startup
_SCHEMA_REGISTRY: Optional[SchemaRegistry] = None
_INTENT_REGISTRY: Optional[IntentRegistry] = None
_AGENT_SETTINGS_REGISTRY: Optional[AgentSettingsRegistry] = None


def initialize_registries(config_dir: str | Path = "config") -> None:
    """
    Initialize all registries from YAML files in config directory.
    
    Call this once at application startup.
    """
    global _SCHEMA_REGISTRY, _INTENT_REGISTRY, _AGENT_SETTINGS_REGISTRY
    
    config_dir = Path(config_dir)
    
    try:
        _SCHEMA_REGISTRY = SchemaRegistry(config_dir / "schema_registry.yaml")
        _INTENT_REGISTRY = IntentRegistry(config_dir / "intents.yaml")
        _AGENT_SETTINGS_REGISTRY = AgentSettingsRegistry(config_dir / "agent_settings.yaml")
        
        logger.info("All registries initialized successfully", config_dir=str(config_dir))
    except Exception as e:
        logger.error("Failed to initialize registries", error=str(e))
        raise


def get_schema_registry() -> SchemaRegistry:
    """Get the global schema registry instance."""
    if _SCHEMA_REGISTRY is None:
        raise RuntimeError("SchemaRegistry not initialized. Call initialize_registries() at startup.")
    return _SCHEMA_REGISTRY


def get_intent_registry() -> IntentRegistry:
    """Get the global intent registry instance."""
    if _INTENT_REGISTRY is None:
        raise RuntimeError("IntentRegistry not initialized. Call initialize_registries() at startup.")
    return _INTENT_REGISTRY


def get_agent_settings_registry() -> AgentSettingsRegistry:
    """Get the global agent settings registry instance."""
    if _AGENT_SETTINGS_REGISTRY is None:
        raise RuntimeError("AgentSettingsRegistry not initialized. Call initialize_registries() at startup.")
    return _AGENT_SETTINGS_REGISTRY
