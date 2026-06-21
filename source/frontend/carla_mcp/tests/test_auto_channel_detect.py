"""Tests for auto-detect mono/stereo in routing tools."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from carla_mcp.backend.backend_bridge import CarlaBackendBridge
from carla_mcp.constants import (
    PATCHBAY_PORT_AUDIO_INPUT_OFFSET,
    PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_host():
    """Create a mock Carla host."""
    host = MagicMock()
    host.is_engine_running = Mock(return_value=True)
    host.get_current_plugin_count = Mock(return_value=2)
    return host


@pytest.fixture
def bridge(mock_host):
    """Create a CarlaBackendBridge with mock host."""
    b = CarlaBackendBridge(mock_host)
    return b


# ---------------------------------------------------------------------------
# Part 1: get_audio_port_counts tests
# ---------------------------------------------------------------------------

class TestGetAudioPortCounts:
    """Test the get_audio_port_counts convenience method."""

    def test_returns_mono_counts(self, bridge, mock_host):
        """Mono plugin returns (1, 1)."""
        info = Mock()
        info.ins = 1
        info.outs = 1
        mock_host.get_audio_port_count_info = Mock(return_value=info)

        result = bridge.get_audio_port_counts(0)
        assert result == (1, 1)

    def test_returns_stereo_counts(self, bridge, mock_host):
        """Stereo plugin returns (2, 2)."""
        info = Mock()
        info.ins = 2
        info.outs = 2
        mock_host.get_audio_port_count_info = Mock(return_value=info)

        result = bridge.get_audio_port_counts(0)
        assert result == (2, 2)

    def test_defaults_on_error(self, bridge, mock_host):
        """Returns (2, 2) when host call raises."""
        mock_host.get_audio_port_count_info = Mock(side_effect=RuntimeError("no plugin"))

        result = bridge.get_audio_port_counts(99)
        assert result == (2, 2)


# ---------------------------------------------------------------------------
# Part 2: Routing tool tests (connect_plugins auto-detect)
# ---------------------------------------------------------------------------

def _make_bridge_and_mcp():
    """Create a bridge with mocked patchbay_connect and plugin info, then register tools."""
    host = MagicMock()
    host.is_engine_running = Mock(return_value=True)
    host.get_current_plugin_count = Mock(return_value=2)

    bridge = CarlaBackendBridge(host)
    # Set up plugin-to-group mapping
    bridge._plugin_to_group_map = {0: 3, 1: 4}
    bridge._group_to_plugin_map = {3: 0, 4: 1}

    # Mock patchbay_connect to always succeed
    bridge.patchbay_connect = Mock(return_value=True)

    # Mock get_plugin_info
    bridge.get_plugin_info = Mock(return_value={"name": "TestPlugin"})

    return bridge, host


def _register_and_get_tools(bridge):
    """Register routing tools and return the tool functions via closure capture."""
    mcp = MagicMock()
    # Capture tool functions as they are registered
    tools = {}

    def capture_tool(**kwargs):
        def decorator(func):
            tools[func.__name__] = func
            return func
        return decorator

    mcp.tool = capture_tool

    from carla_mcp.tools.routing import register_routing_tools
    register_routing_tools(mcp, bridge)
    return tools


class TestConnectPluginsAutoDetect:
    """Test connect_plugins with auto channel detection."""

    def test_stereo_to_stereo(self):
        """stereo->stereo: L->L, R->R (2 connections)."""
        bridge, host = _make_bridge_and_mcp()
        # Both plugins are stereo
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](0, 1)

        assert bridge.patchbay_connect.call_count == 2
        calls = bridge.patchbay_connect.call_args_list
        # L->L
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        # R->R
        assert calls[1] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1)
        assert "Connected" in result

    def test_mono_to_mono(self):
        """mono->mono: 1 connection only."""
        bridge, host = _make_bridge_and_mcp()
        info_mono = Mock()
        info_mono.ins = 1
        info_mono.outs = 1
        host.get_audio_port_count_info = Mock(return_value=info_mono)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](0, 1)

        assert bridge.patchbay_connect.call_count == 1
        calls = bridge.patchbay_connect.call_args_list
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        assert "Connected" in result

    def test_mono_to_stereo(self):
        """mono->stereo: duplicate output to both inputs (2 connections)."""
        bridge, host = _make_bridge_and_mcp()

        def port_counts(plugin_id):
            info = Mock()
            if plugin_id == 0:  # source: mono
                info.ins = 1
                info.outs = 1
            else:  # dest: stereo
                info.ins = 2
                info.outs = 2
            return info

        host.get_audio_port_count_info = Mock(side_effect=port_counts)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](0, 1)

        assert bridge.patchbay_connect.call_count == 2
        calls = bridge.patchbay_connect.call_args_list
        # Same source output 0 -> both dest inputs
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        assert calls[1] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1)
        assert "Connected" in result

    def test_stereo_to_mono(self):
        """stereo->mono: sum both outputs to mono input (2 connections)."""
        bridge, host = _make_bridge_and_mcp()

        def port_counts(plugin_id):
            info = Mock()
            if plugin_id == 0:  # source: stereo
                info.ins = 2
                info.outs = 2
            else:  # dest: mono
                info.ins = 1
                info.outs = 1
            return info

        host.get_audio_port_count_info = Mock(side_effect=port_counts)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](0, 1)

        assert bridge.patchbay_connect.call_count == 2
        calls = bridge.patchbay_connect.call_args_list
        # Both source outputs -> single dest input
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        assert calls[1] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        assert "Connected" in result

    def test_explicit_channel_overrides_auto(self):
        """When user sets channel params explicitly, auto-detect is bypassed."""
        bridge, host = _make_bridge_and_mcp()
        # Plugin is stereo but user requests mono
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](0, 1, source_channel="mono", dest_channel="mono")

        # Should only make 1 connection (user said mono)
        assert bridge.patchbay_connect.call_count == 1


class TestConnectPluginsExplicitCrossChannels:
    """FIX 1: explicit left/right cross combinations must wire correctly, and
    a combination that yields no connections must fail loudly rather than
    report false success (the old code returned ✅ for an empty list)."""

    def test_explicit_left_to_right(self):
        """left->right: a single source out 0 -> dest in 1 connection."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](
            0, 1, source_channel="left", dest_channel="right"
        )

        assert bridge.patchbay_connect.call_count == 1
        calls = bridge.patchbay_connect.call_args_list
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1)
        assert "Connected" in result
        assert "❌" not in result

    def test_explicit_right_to_left(self):
        """right->left: a single source out 1 -> dest in 0 connection."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](
            0, 1, source_channel="right", dest_channel="left"
        )

        assert bridge.patchbay_connect.call_count == 1
        calls = bridge.patchbay_connect.call_args_list
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        assert "Connected" in result
        assert "❌" not in result

    def test_explicit_left_to_left(self):
        """left->left: source out 0 -> dest in 0."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](
            0, 1, source_channel="left", dest_channel="left"
        )

        assert bridge.patchbay_connect.call_count == 1
        calls = bridge.patchbay_connect.call_args_list
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        assert "Connected" in result

    def test_explicit_right_to_right(self):
        """right->right: source out 1 -> dest in 1."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](
            0, 1, source_channel="right", dest_channel="right"
        )

        assert bridge.patchbay_connect.call_count == 1
        calls = bridge.patchbay_connect.call_args_list
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
                                4, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1)
        assert "Connected" in result

    def test_empty_connection_list_reports_failure(self):
        """A combination yielding no connections must fail loudly, not report
        false success. stereo source -> mono dest has no mapping in the
        explicit branch, so the old code returned a false ✅ for 0/0."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugins"](
            0, 1, source_channel="stereo", dest_channel="mono"
        )

        # No connections should be attempted...
        assert bridge.patchbay_connect.call_count == 0
        # ...and the result must be a failure, never a false "Connected".
        assert "❌" in result
        assert "Connected" not in result


# ---------------------------------------------------------------------------
# Part 3: connect_plugin_to_system tests
# ---------------------------------------------------------------------------

class TestConnectPluginToSystem:
    """Test connect_plugin_to_system with auto-detect."""

    def test_mono_plugin_duplicates_to_both_outputs(self):
        """Mono plugin output 0 -> both system outputs."""
        bridge, host = _make_bridge_and_mcp()
        info_mono = Mock()
        info_mono.ins = 1
        info_mono.outs = 1
        host.get_audio_port_count_info = Mock(return_value=info_mono)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugin_to_system"](0, 1)

        assert bridge.patchbay_connect.call_count == 2
        calls = bridge.patchbay_connect.call_args_list
        # Output 0 -> system left
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        # Output 0 -> system right (duplicate)
        assert calls[1] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1)
        assert "Connected" in result

    def test_stereo_plugin_connects_LR(self):
        """Stereo plugin: L->L, R->R."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugin_to_system"](0, 1)

        assert bridge.patchbay_connect.call_count == 2
        calls = bridge.patchbay_connect.call_args_list
        # L->L
        assert calls[0] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        # R->R
        assert calls[1] == call(3, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
                                2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1)
        assert "Connected" in result

    def test_no_partial_warning_for_mono(self):
        """Mono plugin should NOT produce 'Partially connected' warning."""
        bridge, host = _make_bridge_and_mcp()
        info_mono = Mock()
        info_mono.ins = 1
        info_mono.outs = 1
        host.get_audio_port_count_info = Mock(return_value=info_mono)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_plugin_to_system"](0, 1)

        assert "Partially" not in result
        assert "Connected" in result


# ---------------------------------------------------------------------------
# Part 4: connect_system_to_plugin tests
# ---------------------------------------------------------------------------

class TestConnectSystemToPlugin:
    """Test connect_system_to_plugin with auto-detect."""

    def test_mono_plugin_single_connection(self):
        """Mono dest plugin gets single system input connection."""
        bridge, host = _make_bridge_and_mcp()
        info_mono = Mock()
        info_mono.ins = 1
        info_mono.outs = 1
        host.get_audio_port_count_info = Mock(return_value=info_mono)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_system_to_plugin"](1, 0)

        assert bridge.patchbay_connect.call_count == 1
        assert "Connected" in result

    def test_stereo_plugin_pair_connection(self):
        """Stereo dest plugin gets pair connection from system input."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_system_to_plugin"](1, 0)

        assert bridge.patchbay_connect.call_count == 2
        assert "Connected" in result

    def test_stereo_uses_distinct_source_ports(self):
        """FIX 2: stereo mode must map system L (input) and system R (input+1)
        to plugin L and plugin R. The old code wired the SAME source port to
        both plugin inputs, duplicating the mono source."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        # system_input=1 -> source ports OUTPUT_OFFSET+0 (L) and +1 (R)
        result = tools["connect_system_to_plugin"](1, 0)

        assert bridge.patchbay_connect.call_count == 2
        calls = bridge.patchbay_connect.call_args_list
        # System L (output offset + 0) -> plugin L (input offset + 0)
        assert calls[0] == call(1, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                                3, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0)
        # System R (output offset + 1) -> plugin R (input offset + 1)
        assert calls[1] == call(1, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
                                3, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1)
        # The two source ports must be DISTINCT (the bug duplicated one port).
        src_ports = {calls[0].args[1], calls[1].args[1]}
        assert len(src_ports) == 2, "stereo must use two distinct source ports"
        assert "Connected" in result

    def test_explicit_channel_overrides(self):
        """When user sets channel explicitly, auto-detect is bypassed."""
        bridge, host = _make_bridge_and_mcp()
        info_stereo = Mock()
        info_stereo.ins = 2
        info_stereo.outs = 2
        host.get_audio_port_count_info = Mock(return_value=info_stereo)

        tools = _register_and_get_tools(bridge)
        result = tools["connect_system_to_plugin"](1, 0, channel="left")

        assert bridge.patchbay_connect.call_count == 1
