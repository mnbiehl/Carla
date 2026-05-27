"""Tests for rewire_chain_connections helper and rewire_chain MCP tool.

Uses a Mock bridge following the same pattern as test_plugin_handle_tools.py.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, call

import pytest
from fastmcp import FastMCP

from carla_mcp.tools.chain_builder import (
    rewire_chain_connections,
    register_chain_builder_tools,
)
from carla_mcp.constants import (
    PATCHBAY_PORT_AUDIO_INPUT_OFFSET,
    PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bridge(connections: list[dict] | None = None, stereo: bool = True) -> Mock:
    """Return a Mock bridge with configurable patchbay state.

    Args:
        connections: List of connection dicts (must each have an 'id' key).
                     Defaults to an empty list.
        stereo:      If True, all plugins are stereo (2-in/2-out);
                     if False, all plugins are mono (1-in/1-out).
    """
    bridge = Mock()
    bridge.get_patchbay_connections = Mock(return_value=connections or [])
    bridge.patchbay_disconnect = Mock(return_value=True)
    bridge.patchbay_connect = Mock(return_value=True)
    # Simple deterministic group mapping: plugin_id + 100
    bridge._plugin_to_group_map = {}
    if stereo:
        bridge.get_audio_port_counts = Mock(return_value=(2, 2))
    else:
        bridge.get_audio_port_counts = Mock(return_value=(1, 1))
    return bridge


def _add_plugins(bridge: Mock, *plugin_ids: int) -> None:
    """Register plugin IDs in the bridge's group map."""
    for pid in plugin_ids:
        bridge._plugin_to_group_map[pid] = 100 + pid


def _register(bridge: Mock) -> dict:
    """Register chain builder tools and return the tool function map."""
    mcp = FastMCP("test")
    register_chain_builder_tools(mcp, bridge)
    return mcp._tool_manager._tools


# ---------------------------------------------------------------------------
# rewire_chain_connections — unit tests for the helper
# ---------------------------------------------------------------------------


class TestRewireChainConnectionsDisconnect:
    def test_disconnects_all_existing_connections(self):
        conns = [{"id": 10, "group_a": 1}, {"id": 11, "group_a": 2}]
        bridge = _make_bridge(connections=conns)

        rewire_chain_connections(bridge, [])

        bridge.patchbay_disconnect.assert_any_call(10)
        bridge.patchbay_disconnect.assert_any_call(11)
        assert bridge.patchbay_disconnect.call_count == 2

    def test_empty_plugin_ids_makes_no_connect_calls(self):
        conns = [{"id": 5}]
        bridge = _make_bridge(connections=conns)

        result = rewire_chain_connections(bridge, [])

        bridge.patchbay_connect.assert_not_called()
        assert result["success"] is True
        assert result["connections"] == 0
        assert result["plugin_order"] == []

    def test_no_existing_connections_makes_no_disconnect_calls(self):
        bridge = _make_bridge(connections=[])
        _add_plugins(bridge, 0)

        rewire_chain_connections(bridge, [0])

        bridge.patchbay_disconnect.assert_not_called()


class TestRewireChainConnectionsWire:
    def test_single_stereo_plugin_wires_system_in_and_out(self):
        bridge = _make_bridge(stereo=True)
        _add_plugins(bridge, 0)
        g0 = bridge._plugin_to_group_map[0]

        result = rewire_chain_connections(bridge, [0])

        assert result["success"] is True
        # system-in → plugin: 2 connections (stereo)
        # plugin → system-out: 2 connections (stereo)
        assert bridge.patchbay_connect.call_count == 4

        # system group 1 → plugin group
        bridge.patchbay_connect.assert_any_call(
            1, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            g0, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        )
        bridge.patchbay_connect.assert_any_call(
            1, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            g0, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        )
        # plugin group → system group 2
        bridge.patchbay_connect.assert_any_call(
            g0, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        )
        bridge.patchbay_connect.assert_any_call(
            g0, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        )

    def test_two_stereo_plugins_wires_system_in_interplug_system_out(self):
        bridge = _make_bridge(stereo=True)
        _add_plugins(bridge, 0, 1)
        g0 = bridge._plugin_to_group_map[0]
        g1 = bridge._plugin_to_group_map[1]

        result = rewire_chain_connections(bridge, [0, 1])

        assert result["success"] is True
        # system-in→p0 (2) + p0→p1 (2) + p1→system-out (2) = 6 patchbay_connect calls
        assert bridge.patchbay_connect.call_count == 6
        assert result["connections"] == 6

        # p0 → p1 connections
        bridge.patchbay_connect.assert_any_call(
            g0, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            g1, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        )
        bridge.patchbay_connect.assert_any_call(
            g0, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            g1, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        )

    def test_single_mono_plugin_wires_correctly(self):
        bridge = _make_bridge(stereo=False)
        _add_plugins(bridge, 0)
        g0 = bridge._plugin_to_group_map[0]

        result = rewire_chain_connections(bridge, [0])

        assert result["success"] is True
        # system-in→p0 mono: 1 connection
        # p0→system-out mono: 2 (mono plugin duplicated to stereo out)
        assert bridge.patchbay_connect.call_count == 3

    def test_disconnects_before_rewiring(self):
        """Existing connections are removed before new ones are made."""
        conns = [{"id": 7}]
        bridge = _make_bridge(connections=conns, stereo=True)
        _add_plugins(bridge, 0)

        manager = Mock()
        manager.attach_mock(bridge.patchbay_disconnect, "disconnect")
        manager.attach_mock(bridge.patchbay_connect, "connect")

        rewire_chain_connections(bridge, [0])

        # disconnect must appear before any connect in the call list
        all_calls = manager.mock_calls
        disconnect_idx = next(i for i, c in enumerate(all_calls) if c[0] == "disconnect")
        connect_idx = next(i for i, c in enumerate(all_calls) if c[0] == "connect")
        assert disconnect_idx < connect_idx


class TestRewireChainConnectionsReturnValue:
    def test_returns_success_true_and_correct_plugin_order(self):
        bridge = _make_bridge()
        _add_plugins(bridge, 3, 7)

        result = rewire_chain_connections(bridge, [3, 7])

        assert result["success"] is True
        assert result["plugin_order"] == [3, 7]

    def test_returns_success_false_on_exception(self):
        bridge = Mock()
        bridge.get_patchbay_connections = Mock(side_effect=RuntimeError("boom"))

        result = rewire_chain_connections(bridge, [0])

        assert result["success"] is False
        assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# rewire_chain MCP tool — via FastMCP registration pattern
# ---------------------------------------------------------------------------


class TestRewireChainTool:
    def test_tool_registered(self):
        bridge = _make_bridge()
        tools = _register(bridge)
        assert "rewire_chain" in tools

    def test_tool_returns_error_when_no_bridge(self):
        mcp = FastMCP("test")
        register_chain_builder_tools(mcp, None)
        tools = mcp._tool_manager._tools

        result = tools["rewire_chain"].fn(plugin_ids=[])
        data = json.loads(result)
        assert data["success"] is False
        assert "Backend not available" in data["error"]

    def test_tool_calls_rewire_chain_connections_and_returns_json(self):
        bridge = _make_bridge()
        _add_plugins(bridge, 0, 1)
        tools = _register(bridge)

        raw = tools["rewire_chain"].fn(plugin_ids=[0, 1])
        data = json.loads(raw)

        assert data["success"] is True
        assert data["plugin_order"] == [0, 1]

    def test_tool_with_empty_list_disconnects_only(self):
        conns = [{"id": 99}]
        bridge = _make_bridge(connections=conns)
        tools = _register(bridge)

        raw = tools["rewire_chain"].fn(plugin_ids=[])
        data = json.loads(raw)

        assert data["success"] is True
        bridge.patchbay_disconnect.assert_called_once_with(99)
        bridge.patchbay_connect.assert_not_called()
