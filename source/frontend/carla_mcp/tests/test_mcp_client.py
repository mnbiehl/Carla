"""Tests for MCP client."""

import pytest

from carla_mcp.orchestration.mcp_client import ChainMCPClient


class TestChainMCPClient:
    def test_constructs_with_port(self):
        client = ChainMCPClient(port=3002)
        assert client.base_url == "http://127.0.0.1:3002"

    def test_custom_host(self):
        client = ChainMCPClient(port=3005, host="192.168.1.1")
        assert client.base_url == "http://192.168.1.1:3005"

    def test_port_stored(self):
        client = ChainMCPClient(port=3002)
        assert client.port == 3002
