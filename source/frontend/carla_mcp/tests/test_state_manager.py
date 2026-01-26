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
