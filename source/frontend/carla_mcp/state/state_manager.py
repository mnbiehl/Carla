"""
Central state manager for Carla MCP.

Tracks instances, aliases, chains, and connections so the AI
doesn't have to deal with internal IDs.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


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

    def add_connection(self, source: str, destination: str) -> None:
        """Record a connection between source and destination."""
        self.connections.add((source, destination))

    def remove_connection(self, source: str, destination: str) -> None:
        """Remove a connection."""
        self.connections.discard((source, destination))

    def list_connections(self) -> List[Tuple[str, str]]:
        """Return all connections as list of (source, dest) tuples."""
        return list(self.connections)

    def get_connections_from(self, source: str) -> List[str]:
        """Get all destinations connected from a source."""
        return [dest for src, dest in self.connections if src == source]

    def get_connections_to(self, destination: str) -> List[str]:
        """Get all sources connected to a destination."""
        return [src for src, dest in self.connections if dest == destination]
