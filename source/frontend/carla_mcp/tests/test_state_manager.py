"""Tests for StateManager core functionality."""

import pytest
from carla_mcp.state.state_manager import StateManager


class TestStateManagerInit:
    """Test StateManager initialization."""

    def test_creates_empty_state(self):
        """StateManager initializes with empty collections."""
        sm = StateManager()

        assert sm.instances == {}
        assert sm.aliases == {}
        assert sm.chains == {}
        assert sm.connections == set()


class TestAliasOperations:
    """Test alias create/remove/resolve."""

    def test_create_alias(self):
        """Can create an alias for a port name."""
        sm = StateManager()
        sm.create_alias("Guitar Loop", "looper:out_1")

        assert sm.aliases["Guitar Loop"] == "looper:out_1"

    def test_remove_alias(self):
        """Can remove an existing alias."""
        sm = StateManager()
        sm.create_alias("Guitar Loop", "looper:out_1")
        sm.remove_alias("Guitar Loop")

        assert "Guitar Loop" not in sm.aliases

    def test_resolve_alias(self):
        """resolve_name returns real name for alias."""
        sm = StateManager()
        sm.create_alias("Guitar Loop", "looper:out_1")

        assert sm.resolve_name("Guitar Loop") == "looper:out_1"

    def test_resolve_non_alias(self):
        """resolve_name returns input unchanged if not an alias."""
        sm = StateManager()

        assert sm.resolve_name("looper:out_1") == "looper:out_1"

    def test_list_aliases(self):
        """list_aliases returns all aliases."""
        sm = StateManager()
        sm.create_alias("Guitar", "looper:out_1")
        sm.create_alias("Bass", "looper:out_2")

        aliases = sm.list_aliases()
        assert aliases == {"Guitar": "looper:out_1", "Bass": "looper:out_2"}
