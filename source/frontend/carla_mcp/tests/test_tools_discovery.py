"""Tests for new discovery MCP tools."""

import pytest
from unittest.mock import Mock
from carla_mcp.tools_v2.discovery import (
    list_ports,
    list_connections,
    list_instances,
)
from carla_mcp.state import StateManager, InstanceManager, CarlaInstance


@pytest.fixture
def state_manager():
    return StateManager()


@pytest.fixture
def instance_manager():
    return InstanceManager()


class TestListPorts:
    """Test list_ports tool."""

    def test_returns_grouped_ports(self, state_manager, mock_jack_client):
        """Returns ports grouped by type."""
        port1 = Mock(is_input=False, is_audio=True)
        port1.name = "looper:out_1_L"
        port2 = Mock(is_input=True, is_audio=True)
        port2.name = "reverb:in_L"
        port3 = Mock(is_input=True, is_audio=True)
        port3.name = "system:playback_1"
        mock_jack_client.get_ports.return_value = [port1, port2, port3]

        result = list_ports(state_manager, mock_jack_client)

        assert "sources" in result
        assert "destinations" in result
        assert "looper:out_1_L" in result["sources"]


class TestListConnections:
    """Test list_connections tool."""

    def test_returns_all_connections(self, state_manager):
        """Returns all tracked connections."""
        state_manager.add_connection("looper:out_1_L", "reverb:in_L")
        state_manager.add_connection("reverb:out_L", "system:playback_1")

        result = list_connections(state_manager)

        assert len(result) == 2


class TestListInstances:
    """Test list_instances tool."""

    def test_returns_instance_info(self, instance_manager):
        """Returns info about all instances."""
        instance = CarlaInstance(name="main", headless=True)
        instance_manager.register(instance)

        result = list_instances(instance_manager)

        assert len(result) == 1
        assert result[0]["name"] == "main"
        assert result[0]["running"] is False
