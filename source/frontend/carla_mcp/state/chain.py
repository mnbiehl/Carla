"""
Chain data structure for grouped audio routing.

A chain represents a signal path: source -> plugin1 -> plugin2 -> destination
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class Chain:
    """A named chain of audio components."""

    name: str
    components: List[str]  # Ordered list: source, plugins..., destination
    instance: str  # Which Carla instance this chain lives on

    def get_connection_pairs(self) -> List[Tuple[str, str]]:
        """Generate (source, dest) pairs for all connections in chain."""
        if len(self.components) < 2:
            return []

        pairs = []
        for i in range(len(self.components) - 1):
            pairs.append((self.components[i], self.components[i + 1]))
        return pairs

    @property
    def source(self) -> Optional[str]:
        """First component (audio source)."""
        return self.components[0] if self.components else None

    @property
    def destination(self) -> Optional[str]:
        """Last component (audio destination)."""
        return self.components[-1] if self.components else None
