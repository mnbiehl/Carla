"""Shared test fixtures for Carla MCP tests."""

import pytest
from unittest.mock import Mock, MagicMock

# Avoid importing the full carla_mcp package which may have dependency issues
# Tests should import specific modules directly instead


@pytest.fixture
def mock_jack_client():
    """Mock JACK client for testing without real JACK."""
    client = Mock()
    client.get_ports = Mock(return_value=[])
    client.connect = Mock()
    client.disconnect = Mock()
    return client


@pytest.fixture
def mock_carla_host():
    """Mock Carla host instance for testing without real Carla."""
    host = MagicMock()
    host.is_engine_running = Mock(return_value=True)
    host.get_current_plugin_count = Mock(return_value=0)
    host.add_plugin = Mock(return_value=True)
    host.remove_plugin = Mock(return_value=True)
    host.get_plugin_info = Mock(return_value={
        "name": "Test Plugin",
        "label": "test",
        "type": 4,  # LV2
    })
    return host
