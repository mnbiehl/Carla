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
