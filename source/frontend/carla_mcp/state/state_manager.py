"""
Central state manager for Carla MCP.

Tracks instances, aliases, chains, and connections so the AI
doesn't have to deal with internal IDs.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Tuple


@dataclass
class StateManager:
    """Manages all MCP state: instances, aliases, chains, connections."""

    instances: Dict[str, "CarlaInstance"] = field(default_factory=dict)
    aliases: Dict[str, str] = field(default_factory=dict)  # alias -> real_name
    chains: Dict[str, "Chain"] = field(default_factory=dict)
    connections: Set[Tuple[str, str]] = field(default_factory=set)  # (source, dest)

    def create_alias(self, alias: str, target: str) -> None:
        """Create an alias for a port/plugin name."""
        self.aliases[alias] = target

    def remove_alias(self, alias: str) -> None:
        """Remove an alias."""
        self.aliases.pop(alias, None)

    def resolve_name(self, name: str) -> str:
        """Resolve an alias to its real name, or return unchanged."""
        return self.aliases.get(name, name)

    def list_aliases(self) -> Dict[str, str]:
        """Return all aliases."""
        return dict(self.aliases)
