"""Tests for build_effects_chain tool (chain_builder module)."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from carla_mcp.tools.chain_builder import build_chain, _make_connections
from carla_mcp.constants import (
    PATCHBAY_PORT_AUDIO_INPUT_OFFSET,
    PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET,
)


def _make_bridge(plugin_count_start=0, stereo_plugins=None):
    """Create a mock bridge with configurable plugin behavior.

    Args:
        plugin_count_start: Initial plugin count (increments per add).
        stereo_plugins: Set of plugin IDs that should be stereo (2-in, 2-out).
                        Plugins not in this set are mono (1-in, 1-out).
                        If None, all plugins default to stereo.
    """
    bridge = Mock()
    # Track how many plugins have been added so far
    bridge._current_count = plugin_count_start
    bridge._plugin_to_group_map = {}

    def add_plugin_side_effect(name):
        pid = bridge._current_count
        group_id = 100 + pid  # deterministic group IDs
        bridge._plugin_to_group_map[pid] = group_id
        bridge._current_count += 1
        return (True, "ok")

    bridge.add_plugin_by_name = Mock(side_effect=add_plugin_side_effect)
    bridge.remove_plugin = Mock(return_value=True)
    bridge.patchbay_connect = Mock(return_value=True)

    def get_audio_port_counts(pid):
        if stereo_plugins is None:
            return (2, 2)
        if pid in stereo_plugins:
            return (2, 2)
        return (1, 1)

    bridge.get_audio_port_counts = Mock(side_effect=get_audio_port_counts)
    bridge.get_plugin_count = Mock(side_effect=lambda: bridge._current_count)

    return bridge


class TestBuildChainOfThreePlugins:
    """test_builds_chain_of_three_plugins — 3 plugins added, 2 inter-plugin connections made."""

    def test_builds_chain_of_three_plugins(self):
        bridge = _make_bridge()
        result = build_chain(bridge, ["EQ", "Compressor", "Reverb"])

        assert result["success"] is True
        assert len(result["plugins"]) == 3
        # 3 stereo plugins: 2 boundaries × 2 connections each = 4 patchbay_connect calls
        assert bridge.patchbay_connect.call_count == 4
        assert bridge.add_plugin_by_name.call_count == 3

    def test_returned_plugin_ids_are_sequential(self):
        bridge = _make_bridge(plugin_count_start=0)
        result = build_chain(bridge, ["A", "B", "C"])

        assert result["plugins"] == [
            {"id": 0, "name": "A"},
            {"id": 1, "name": "B"},
            {"id": 2, "name": "C"},
        ]


class TestRollbackOnPluginLoadFailure:
    """test_rolls_back_on_plugin_load_failure — second plugin fails, first gets removed."""

    def test_rolls_back_on_plugin_load_failure(self):
        bridge = _make_bridge()

        call_count = [0]
        def add_side_effect(name):
            pid = bridge._current_count
            if call_count[0] == 1:
                # Second plugin fails
                call_count[0] += 1
                return (False, "plugin not found")
            group_id = 100 + pid
            bridge._plugin_to_group_map[pid] = group_id
            bridge._current_count += 1
            call_count[0] += 1
            return (True, "ok")

        bridge.add_plugin_by_name = Mock(side_effect=add_side_effect)

        result = build_chain(bridge, ["EQ", "BadPlugin", "Reverb"])

        assert result["success"] is False
        assert "BadPlugin" in result["error"]
        # First plugin (id=0) should be rolled back
        bridge.remove_plugin.assert_called_once_with(0)


class TestMonoToStereo:
    """test_mono_to_stereo_at_boundary — mono→stereo makes 2 connections (duplicate)."""

    def test_mono_to_stereo_at_boundary(self):
        # Plugin 0 is mono, plugin 1 is stereo
        bridge = _make_bridge(stereo_plugins={1})

        result = build_chain(bridge, ["MonoFX", "StereoFX"])

        assert result["success"] is True
        # mono→stereo: out_0→in_0, out_0→in_1 = 2 connections
        assert bridge.patchbay_connect.call_count == 2

        src_group = bridge._plugin_to_group_map[0]
        dst_group = bridge._plugin_to_group_map[1]
        bridge.patchbay_connect.assert_any_call(
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        )
        bridge.patchbay_connect.assert_any_call(
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        )


class TestStereoToMono:
    """test_stereo_to_mono_sums — stereo→mono makes 2 connections (both to input 0)."""

    def test_stereo_to_mono_sums(self):
        # Plugin 0 is stereo, plugin 1 is mono
        bridge = _make_bridge(stereo_plugins={0})

        result = build_chain(bridge, ["StereoFX", "MonoFX"])

        assert result["success"] is True
        # stereo→mono: out_0→in_0, out_1→in_0 = 2 connections
        assert bridge.patchbay_connect.call_count == 2

        src_group = bridge._plugin_to_group_map[0]
        dst_group = bridge._plugin_to_group_map[1]
        bridge.patchbay_connect.assert_any_call(
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        )
        bridge.patchbay_connect.assert_any_call(
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        )


class TestConnectSystemInput:
    """test_connect_system_input_to_first_plugin — system group 1 connected to first plugin."""

    def test_connect_system_input_to_first_plugin(self):
        bridge = _make_bridge()  # all stereo by default

        result = build_chain(bridge, ["EQ", "Compressor"], connect_system_input=True)

        assert result["success"] is True
        first_group = bridge._plugin_to_group_map[0]
        # System input (group 1) stereo out → first plugin stereo in
        bridge.patchbay_connect.assert_any_call(
            1, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            first_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        )
        bridge.patchbay_connect.assert_any_call(
            1, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            first_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        )


class TestAutoWireMonitors:
    """build_chain with connect_system_output=True should call ensure_carla_to_monitors."""

    @patch("carla_mcp.tools.chain_builder.ensure_carla_to_monitors")
    def test_calls_ensure_carla_to_monitors_when_system_output(self, mock_ensure):
        mock_ensure.return_value = {
            "connected": 1, "already_connected": 1, "failed": 0,
            "monitor_ports": ["mon:AUX0", "mon:AUX1"],
        }
        bridge = _make_bridge()
        result = build_chain(bridge, ["EQ"], connect_system_output=True)

        assert result["success"] is True
        mock_ensure.assert_called_once()
        assert "external_monitors" in result

    @patch("carla_mcp.tools.chain_builder.ensure_carla_to_monitors")
    def test_skips_monitor_wire_when_no_system_output(self, mock_ensure):
        bridge = _make_bridge()
        result = build_chain(bridge, ["EQ"], connect_system_output=False)

        assert result["success"] is True
        mock_ensure.assert_not_called()
        assert "external_monitors" not in result


class TestConnectSystemOutput:
    """test_connect_last_plugin_to_system_output — last plugin connected to system group 2."""

    def test_connect_last_plugin_to_system_output(self):
        bridge = _make_bridge()  # all stereo by default

        result = build_chain(bridge, ["EQ", "Compressor"], connect_system_output=True)

        assert result["success"] is True
        last_group = bridge._plugin_to_group_map[1]
        # Last plugin stereo out → system output (group 2) stereo in
        bridge.patchbay_connect.assert_any_call(
            last_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        )
        bridge.patchbay_connect.assert_any_call(
            last_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        )
