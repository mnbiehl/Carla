"""Tests for rig/register.py — register_rig_tools MCP tool registration.

Verifies all 14 tools are registered and that tool functions forward
correctly to the controller.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP

from carla_mcp.rig.register import register_rig_tools
from carla_mcp.rig.graph import RigGraph, Node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "describe_rig",
    "create_track",
    "create_bus",
    "remove_node",
    "add_effect",
    "remove_effect",
    "move_effect",
    "set_param",
    "bypass",
    "route",
    "unroute",
    "list_io",
    "alias_input",
    "find_plugins",
    "export_rig_state",
    "import_rig_state",
}


def _make_mcp_and_controller():
    """Return a (FastMCP, mock_controller) pair after registering rig tools."""
    mcp = FastMCP("test")
    controller = MagicMock()
    # Async methods need AsyncMock so they are awaitable
    controller.add_effect = AsyncMock(return_value={"success": True})
    controller.remove_effect = AsyncMock(return_value={"success": True})
    controller.move_effect = AsyncMock(return_value={"success": True})
    controller.set_param = AsyncMock(return_value={"success": True})
    controller.bypass = AsyncMock(return_value={"success": True})
    controller.export_rig_state = AsyncMock(return_value={"version": 1, "nodes": [], "edges": []})
    controller.import_rig_state = AsyncMock(return_value={"success": True, "tracks": []})
    controller._graph = RigGraph()
    register_rig_tools(mcp, controller)
    return mcp, controller


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_all_16_tools_are_registered(self):
        mcp, _ = _make_mcp_and_controller()
        registered = set(mcp._tool_manager._tools.keys())
        assert EXPECTED_TOOLS == registered

    def test_tool_count_is_exactly_16(self):
        mcp, _ = _make_mcp_and_controller()
        assert len(mcp._tool_manager._tools) == 16


# ---------------------------------------------------------------------------
# Sync tool forwarding
# ---------------------------------------------------------------------------


class TestSyncToolForwarding:
    def test_describe_rig_calls_describe_with_graph(self):
        """describe_rig tool calls describe_rig(controller._graph)."""
        mcp, controller = _make_mcp_and_controller()
        # Put a node in the graph so describe_rig returns something non-trivial
        controller._graph.add_node(Node(name="strat", kind="track"))
        tools = mcp._tool_manager._tools
        result = tools["describe_rig"].fn()
        assert isinstance(result, str)
        # Should include the node name in the chains section
        assert "strat" in result

    def test_create_track_forwards_to_controller(self):
        mcp, controller = _make_mcp_and_controller()
        controller.create_track.return_value = {"success": True, "name": "strat"}
        tools = mcp._tool_manager._tools
        result = tools["create_track"].fn(name="strat", source="in:guitar")
        controller.create_track.assert_called_once_with("strat", "in:guitar")
        assert result["success"] is True

    def test_create_bus_forwards_to_controller(self):
        mcp, controller = _make_mcp_and_controller()
        controller.create_bus.return_value = {"success": True, "name": "reverb"}
        tools = mcp._tool_manager._tools
        result = tools["create_bus"].fn(name="reverb")
        controller.create_bus.assert_called_once_with("reverb")
        assert result["success"] is True

    def test_remove_node_forwards_to_controller(self):
        mcp, controller = _make_mcp_and_controller()
        controller.remove_node.return_value = {"success": True}
        tools = mcp._tool_manager._tools
        result = tools["remove_node"].fn(name="strat")
        controller.remove_node.assert_called_once_with("strat")

    def test_route_forwards_to_controller(self):
        mcp, controller = _make_mcp_and_controller()
        controller.route.return_value = {"success": True, "pairs": []}
        tools = mcp._tool_manager._tools
        result = tools["route"].fn(src="strat", dst="out:main")
        controller.route.assert_called_once_with("strat", "out:main")

    def test_unroute_forwards_to_controller(self):
        mcp, controller = _make_mcp_and_controller()
        controller.unroute.return_value = {"success": True, "disconnect_failures": 0}
        tools = mcp._tool_manager._tools
        result = tools["unroute"].fn(src="strat", dst="out:main")
        controller.unroute.assert_called_once_with("strat", "out:main")

    def test_list_io_forwards_to_controller(self):
        mcp, controller = _make_mcp_and_controller()
        controller.list_io.return_value = {"sources": [], "sinks": [], "aliases": {}}
        tools = mcp._tool_manager._tools
        result = tools["list_io"].fn()
        controller.list_io.assert_called_once_with()

    def test_alias_input_forwards_to_controller(self):
        mcp, controller = _make_mcp_and_controller()
        controller.alias_input.return_value = {"success": True, "name": "in:guitar", "port": "alsa:capture_0"}
        tools = mcp._tool_manager._tools
        result = tools["alias_input"].fn(port="alsa:capture_0", name="in:guitar")
        controller.alias_input.assert_called_once_with("alsa:capture_0", "in:guitar")

    def test_find_plugins_passes_none_for_empty_strings(self):
        mcp, controller = _make_mcp_and_controller()
        controller.find_plugins.return_value = {"success": True, "plugins": []}
        tools = mcp._tool_manager._tools
        tools["find_plugins"].fn(query="", category="")
        controller.find_plugins.assert_called_once_with(query=None, category=None)

    def test_find_plugins_passes_values_when_given(self):
        mcp, controller = _make_mcp_and_controller()
        controller.find_plugins.return_value = {"success": True, "plugins": []}
        tools = mcp._tool_manager._tools
        tools["find_plugins"].fn(query="LSP", category="Dynamics")
        controller.find_plugins.assert_called_once_with(query="LSP", category="Dynamics")


# ---------------------------------------------------------------------------
# Async tool forwarding
# ---------------------------------------------------------------------------


class TestAsyncToolForwarding:
    def test_add_effect_is_async_and_forwards(self):
        mcp, controller = _make_mcp_and_controller()
        tools = mcp._tool_manager._tools
        coro = tools["add_effect"].fn(node="strat", plugin="mcomp", role="comp", position="end")
        result = asyncio.run(coro)
        controller.add_effect.assert_called_once_with("strat", "mcomp", "comp", "end")
        assert result["success"] is True

    def test_remove_effect_is_async_and_forwards(self):
        mcp, controller = _make_mcp_and_controller()
        tools = mcp._tool_manager._tools
        coro = tools["remove_effect"].fn(node="strat", effect="comp")
        result = asyncio.run(coro)
        controller.remove_effect.assert_called_once_with("strat", "comp")
        assert result["success"] is True

    def test_bypass_is_async_and_forwards(self):
        mcp, controller = _make_mcp_and_controller()
        tools = mcp._tool_manager._tools
        coro = tools["bypass"].fn(node="strat", effect="comp", on=True)
        result = asyncio.run(coro)
        controller.bypass.assert_called_once_with("strat", "comp", True)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Probe tools (optional)
# ---------------------------------------------------------------------------


PROBE_TOOLS = {"play_tone", "stop_tone", "measure_level"}


def _make_mcp_with_probe():
    mcp = FastMCP("test")
    controller = MagicMock()
    controller._graph = RigGraph()
    probe = MagicMock()
    probe.play_tone = AsyncMock(return_value={"success": True})
    probe.measure_level = AsyncMock(return_value={"success": True})
    register_rig_tools(mcp, controller, probe=probe)
    return mcp, controller, probe


class TestProbeRegistration:
    def test_probe_omitted_means_only_16_tools(self):
        mcp = FastMCP("test")
        controller = MagicMock()
        controller._graph = RigGraph()
        register_rig_tools(mcp, controller)
        assert len(mcp._tool_manager._tools) == 16
        assert PROBE_TOOLS.isdisjoint(mcp._tool_manager._tools.keys())

    def test_probe_adds_three_tools(self):
        mcp, _, _ = _make_mcp_with_probe()
        registered = set(mcp._tool_manager._tools.keys())
        assert EXPECTED_TOOLS | PROBE_TOOLS == registered
        assert len(registered) == 19

    def test_play_tone_forwards_to_probe(self):
        mcp, _, probe = _make_mcp_with_probe()
        tools = mcp._tool_manager._tools
        coro = tools["play_tone"].fn(node="strat", hz=440.0, db=-12.0, at="input")
        result = asyncio.run(coro)
        probe.play_tone.assert_called_once_with("strat", hz=440.0, db=-12.0, at="input")
        assert result["success"] is True

    def test_stop_tone_forwards_to_probe(self):
        mcp, _, probe = _make_mcp_with_probe()
        probe.stop_tone.return_value = {"success": True}
        tools = mcp._tool_manager._tools
        result = tools["stop_tone"].fn(node="strat")
        probe.stop_tone.assert_called_once_with("strat")
        assert result["success"] is True

    def test_measure_level_forwards_to_probe(self):
        mcp, _, probe = _make_mcp_with_probe()
        tools = mcp._tool_manager._tools
        coro = tools["measure_level"].fn(node="strat", at="output", duration=0.5)
        result = asyncio.run(coro)
        probe.measure_level.assert_called_once_with("strat", at="output", duration=0.5)
        assert result["success"] is True
