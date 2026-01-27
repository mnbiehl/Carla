"""Tests for Chain data structure."""

import pytest
from carla_mcp.state.chain import Chain


class TestChainCreation:
    """Test chain creation and properties."""

    def test_create_chain(self):
        """Can create a chain with name and components."""
        chain = Chain(
            name="Guitar FX",
            components=["looper:out_1", "Compressor", "Reverb", "system:playback"],
            instance="main"
        )

        assert chain.name == "Guitar FX"
        assert len(chain.components) == 4
        assert chain.instance == "main"

    def test_chain_generates_connections(self):
        """Chain generates connection pairs from components."""
        chain = Chain(
            name="Simple",
            components=["A", "B", "C"],
            instance="main"
        )

        connections = chain.get_connection_pairs()

        assert connections == [("A", "B"), ("B", "C")]

    def test_empty_chain_no_connections(self):
        """Chain with 0-1 components has no connections."""
        chain = Chain(name="Empty", components=[], instance="main")
        assert chain.get_connection_pairs() == []

        chain = Chain(name="Single", components=["A"], instance="main")
        assert chain.get_connection_pairs() == []

    def test_chain_source_and_dest(self):
        """Chain knows its source and destination."""
        chain = Chain(
            name="Test",
            components=["looper:out_1", "Reverb", "system:playback"],
            instance="main"
        )

        assert chain.source == "looper:out_1"
        assert chain.destination == "system:playback"
