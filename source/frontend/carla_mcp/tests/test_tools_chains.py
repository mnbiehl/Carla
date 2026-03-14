"""Tests for chain MCP tools."""

import pytest
from unittest.mock import Mock
from carla_mcp.tools_v2.chains import create_chain, delete_chain, ChainResult
from carla_mcp.state import StateManager


@pytest.fixture
def state_manager():
    return StateManager()


@pytest.fixture
def mock_jack_client():
    client = Mock()
    client.connect = Mock()
    client.disconnect = Mock()
    return client


class TestCreateChain:
    """Test create_chain tool."""

    def test_creates_chain_with_connections(self, state_manager, mock_jack_client):
        """Creates chain and makes all connections."""
        result = create_chain(
            state_manager,
            mock_jack_client,
            name="Test Chain",
            components=["looper:out_1_L", "Compressor:in_L"],
            instance="main"
        )

        assert result.success
        assert "Test Chain" in state_manager.chains
        assert mock_jack_client.connect.called

    def test_chain_tracks_all_connections(self, state_manager, mock_jack_client):
        """Chain records all its connections in state."""
        create_chain(
            state_manager,
            mock_jack_client,
            name="Test",
            components=["looper:out_1_L", "Compressor:in_L"],
            instance="main"
        )

        chain = state_manager.chains["Test"]
        assert len(chain.components) == 2


class TestDeleteChain:
    """Test delete_chain tool."""

    def test_deletes_chain_and_connections(self, state_manager, mock_jack_client):
        """Deleting chain removes it and disconnects."""
        create_chain(
            state_manager,
            mock_jack_client,
            name="Test",
            components=["looper:out_1_L", "Compressor:in_L"],
            instance="main"
        )

        result = delete_chain(state_manager, mock_jack_client, name="Test")

        assert result.success
        assert "Test" not in state_manager.chains
        mock_jack_client.disconnect.assert_called()

    def test_delete_nonexistent_chain_fails(self, state_manager, mock_jack_client):
        """Deleting nonexistent chain returns error."""
        result = delete_chain(state_manager, mock_jack_client, name="Nonexistent")

        assert not result.success
