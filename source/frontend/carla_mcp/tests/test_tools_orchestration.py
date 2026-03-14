"""Tests for orchestration MCP tools."""
import pytest
from unittest.mock import Mock, patch
from fastmcp import FastMCP
from carla_mcp.state.instance_manager import InstanceManager
from carla_mcp.orchestration.chain_launcher import ChainLauncher
from carla_mcp.orchestration.jack_router import JackRouter


@pytest.fixture
def mcp():
    return FastMCP("test")


@pytest.fixture
def instance_manager():
    return InstanceManager(base_mcp_port=3002)


@pytest.fixture
def launcher(instance_manager):
    return ChainLauncher(instance_manager=instance_manager, carla_script="/fake/carla.py")


@pytest.fixture
def router():
    return JackRouter()


class TestOrchestrationToolRegistration:
    def test_tools_are_registered(self, mcp, launcher, router, instance_manager):
        from carla_mcp.tools.orchestration import register_orchestration_tools
        register_orchestration_tools(mcp, launcher, router, instance_manager)
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "create_effects_chain" in tool_names
        assert "destroy_effects_chain" in tool_names
        assert "list_effects_chains" in tool_names
        assert "route_track_to_chain" in tool_names
        assert "route_chain_to_main" in tool_names
        assert "get_routing_overview" in tool_names
