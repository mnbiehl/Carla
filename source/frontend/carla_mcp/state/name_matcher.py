"""
Port name matching with fuzzy/partial support.

Exact names execute immediately.
Partial names return candidates for user confirmation.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class MatchResult:
    """Result of a name match attempt."""

    query: str
    matches: List[str]
    is_exact: bool

    @property
    def needs_confirmation(self) -> bool:
        """True if multiple matches require user to pick one."""
        return not self.is_exact and len(self.matches) > 1


class NameMatcher:
    """Matches port names with exact and fuzzy matching."""

    def __init__(self, available_names: List[str]):
        """Initialize with list of available port names."""
        self.available = available_names
        self.available_lower = [n.lower() for n in available_names]

    def match(self, query: str) -> MatchResult:
        """Match a query against available names.

        Args:
            query: Port name to match (exact or partial)

        Returns:
            MatchResult with matches and whether it's exact
        """
        # Try exact match first
        if query in self.available:
            return MatchResult(query=query, matches=[query], is_exact=True)

        # Try case-insensitive exact match
        query_lower = query.lower()
        for i, name_lower in enumerate(self.available_lower):
            if name_lower == query_lower:
                return MatchResult(
                    query=query,
                    matches=[self.available[i]],
                    is_exact=True
                )

        # Fuzzy match: find all names containing the query
        matches = []
        for i, name_lower in enumerate(self.available_lower):
            if query_lower in name_lower:
                matches.append(self.available[i])

        # Also match if query is prefix of client name (before colon)
        for i, name in enumerate(self.available):
            if ":" in name:
                client = name.split(":")[0]
                if client.lower() == query_lower:
                    if self.available[i] not in matches:
                        matches.append(self.available[i])

        return MatchResult(query=query, matches=matches, is_exact=False)
