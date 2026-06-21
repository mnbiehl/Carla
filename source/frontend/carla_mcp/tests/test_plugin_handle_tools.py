"""Tests for handle MCP tools in tools/plugins.py.

Uses a real FastMCP instance with a Mock backend_bridge.  Tools are captured
via mcp._tool_manager._tools[name].fn(...).
"""

import json
import pytest
from unittest.mock import Mock
from fastmcp import FastMCP

from carla_mcp.tools.plugins import register_plugin_tools
from carla_mcp.rig.handles import HANDLE_KEY


# ---------------------------------------------------------------------------
# Shared setup helpers


def _make_bridge(plugin_count: int = 0) -> Mock:
    bridge = Mock()
    bridge.get_plugin_count = Mock(return_value=plugin_count)
    bridge.set_custom_data = Mock(return_value=True)
    bridge.get_custom_data_value = Mock(return_value=None)
    return bridge


def _register(bridge: Mock) -> dict:
    """Register plugin tools and return the tool function map."""
    mcp = FastMCP("test")
    register_plugin_tools(mcp, bridge)
    return mcp._tool_manager._tools


# ---------------------------------------------------------------------------
# set_plugin_handle


class TestSetPluginHandle:
    def test_calls_set_custom_data_with_correct_args(self):
        bridge = _make_bridge()
        tools = _register(bridge)

        tools["set_plugin_handle"].fn(plugin_id=2, handle="strat/comp")

        bridge.set_custom_data.assert_called_once_with(2, "string", HANDLE_KEY, "strat/comp")

    def test_returns_success_message_on_true(self):
        bridge = _make_bridge()
        bridge.set_custom_data.return_value = True
        tools = _register(bridge)

        result = tools["set_plugin_handle"].fn(plugin_id=0, handle="bass/di")

        assert "✅" in result
        assert "0" in result

    def test_returns_failure_message_on_false(self):
        bridge = _make_bridge()
        bridge.set_custom_data.return_value = False
        tools = _register(bridge)

        result = tools["set_plugin_handle"].fn(plugin_id=1, handle="x")

        assert "❌" in result

    def test_returns_error_when_no_bridge(self):
        mcp = FastMCP("test")
        register_plugin_tools(mcp, None)
        tools = mcp._tool_manager._tools

        result = tools["set_plugin_handle"].fn(plugin_id=0, handle="h")

        assert "❌" in result


# ---------------------------------------------------------------------------
# get_plugin_handle


class TestGetPluginHandle:
    def test_returns_stamped_handle(self):
        bridge = _make_bridge()
        bridge.get_custom_data_value.return_value = "strat/comp"
        tools = _register(bridge)

        result = tools["get_plugin_handle"].fn(plugin_id=0)

        bridge.get_custom_data_value.assert_called_once_with(0, "string", HANDLE_KEY)
        assert result == "strat/comp"

    def test_returns_empty_string_when_not_stamped(self):
        bridge = _make_bridge()
        bridge.get_custom_data_value.return_value = None
        tools = _register(bridge)

        result = tools["get_plugin_handle"].fn(plugin_id=5)

        assert result == ""

    def test_returns_error_when_no_bridge(self):
        mcp = FastMCP("test")
        register_plugin_tools(mcp, None)
        tools = mcp._tool_manager._tools

        result = tools["get_plugin_handle"].fn(plugin_id=0)

        assert "❌" in result


# ---------------------------------------------------------------------------
# list_plugin_handles


class TestListPluginHandles:
    def test_returns_json_with_plugins_that_have_handles(self):
        bridge = _make_bridge(plugin_count=3)

        def _get_handle(pid, type_, key):
            return {0: "strat/comp", 2: "strat/amp"}.get(pid)

        bridge.get_custom_data_value.side_effect = _get_handle
        tools = _register(bridge)

        raw = tools["list_plugin_handles"].fn()
        data = json.loads(raw)

        assert data == {"0": "strat/comp", "2": "strat/amp"}

    def test_excludes_plugins_without_handles(self):
        bridge = _make_bridge(plugin_count=2)
        bridge.get_custom_data_value.return_value = None
        tools = _register(bridge)

        raw = tools["list_plugin_handles"].fn()
        data = json.loads(raw)

        assert data == {}

    def test_empty_when_no_plugins(self):
        bridge = _make_bridge(plugin_count=0)
        tools = _register(bridge)

        raw = tools["list_plugin_handles"].fn()
        data = json.loads(raw)

        assert data == {}

    def test_calls_get_plugin_count(self):
        bridge = _make_bridge(plugin_count=5)
        bridge.get_custom_data_value.return_value = None
        tools = _register(bridge)

        tools["list_plugin_handles"].fn()

        bridge.get_plugin_count.assert_called_once()

    def test_returns_error_when_no_bridge(self):
        mcp = FastMCP("test")
        register_plugin_tools(mcp, None)
        tools = mcp._tool_manager._tools

        result = tools["list_plugin_handles"].fn()

        assert "❌" in result
