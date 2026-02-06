"""Tests for routing MCP tools."""

import pytest
from unittest.mock import Mock, call
from carla_mcp.tools_v2.routing import connect, disconnect, ConnectResult
from carla_mcp.state import StateManager


def _make_port(name, is_input, is_audio=True):
    """Create a mock JACK port, avoiding Mock(name=...) gotcha."""
    port = Mock(is_input=is_input, is_audio=is_audio)
    port.name = name
    return port


@pytest.fixture
def state_manager():
    return StateManager()


@pytest.fixture
def mock_jack_client():
    client = Mock()
    client.connect = Mock()
    client.disconnect = Mock()
    client.get_ports = Mock(return_value=[
        _make_port("looper:out_1_L", is_input=False),
        _make_port("looper:out_1_R", is_input=False),
        _make_port("reverb:in_L", is_input=True),
        _make_port("reverb:in_R", is_input=True),
    ])
    return client


class TestConnect:
    """Test connect tool."""

    def test_exact_match_connects_immediately(self, state_manager, mock_jack_client):
        """Exact port names connect without confirmation."""
        result = connect(
            state_manager,
            mock_jack_client,
            source="looper:out_1_L",
            destination="reverb:in_L"
        )

        assert result.success
        assert result.needs_confirmation is False
        mock_jack_client.connect.assert_called_once()

    def test_connection_tracked_in_state(self, state_manager, mock_jack_client):
        """Successful connection is recorded in state."""
        connect(
            state_manager,
            mock_jack_client,
            source="looper:out_1_L",
            destination="reverb:in_L"
        )

        assert ("looper:out_1_L", "reverb:in_L") in state_manager.connections

    def test_partial_match_returns_candidates(self, state_manager, mock_jack_client):
        """Partial names return candidates for confirmation."""
        result = connect(
            state_manager,
            mock_jack_client,
            source="looper",
            destination="reverb"
        )

        assert not result.success
        assert result.needs_confirmation
        assert len(result.source_matches) > 0
        mock_jack_client.connect.assert_not_called()

    def test_stereo_auto_mode_connects_pair(self, state_manager, mock_jack_client):
        """Auto mode connects stereo pairs L→L, R→R."""
        result = connect(
            state_manager,
            mock_jack_client,
            source="looper:out_1",
            destination="reverb:in",
            mode="auto"
        )

        assert mock_jack_client.connect.call_count == 2


class TestDisconnect:
    """Test disconnect tool."""

    def test_disconnect_removes_connection(self, state_manager, mock_jack_client):
        """Disconnect removes from JACK and state."""
        state_manager.add_connection("looper:out_1_L", "reverb:in_L")

        result = disconnect(
            state_manager,
            mock_jack_client,
            source="looper:out_1_L",
            destination="reverb:in_L"
        )

        assert result.success
        mock_jack_client.disconnect.assert_called_once()
        assert ("looper:out_1_L", "reverb:in_L") not in state_manager.connections
