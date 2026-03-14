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


class TestConnectionTracking:
    """Test connection add/remove/query."""

    def test_add_connection(self):
        """Can add a connection."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")

        assert ("looper:out_1_L", "reverb:in_L") in sm.connections

    def test_remove_connection(self):
        """Can remove a connection."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")
        sm.remove_connection("looper:out_1_L", "reverb:in_L")

        assert ("looper:out_1_L", "reverb:in_L") not in sm.connections

    def test_list_connections(self):
        """Can list all connections."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")
        sm.add_connection("looper:out_1_R", "reverb:in_R")

        conns = sm.list_connections()
        assert len(conns) == 2

    def test_get_connections_from(self):
        """Can get all connections from a source."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")
        sm.add_connection("looper:out_1_L", "delay:in_L")
        sm.add_connection("looper:out_2_L", "chorus:in_L")

        conns = sm.get_connections_from("looper:out_1_L")
        assert len(conns) == 2
        assert "reverb:in_L" in conns
        assert "delay:in_L" in conns

    def test_get_connections_to(self):
        """Can get all connections to a destination."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")
        sm.add_connection("looper:out_2_L", "reverb:in_L")

        conns = sm.get_connections_to("reverb:in_L")
        assert len(conns) == 2
