"""Tests for chain preset save/load/list tools."""

import json
import pytest
from unittest.mock import Mock, patch

from carla_mcp.tools.chain_presets import (
    save_chain_preset_impl,
    load_chain_preset_impl,
    list_chain_presets_impl,
    CHAIN_PRESET_DIR,
)


def _make_bridge(plugin_count_start=0):
    """Create a mock bridge for chain preset tests."""
    bridge = Mock()
    bridge._current_count = plugin_count_start
    bridge._plugin_to_group_map = {}

    def add_plugin_side_effect(name):
        pid = bridge._current_count
        group_id = 100 + pid
        bridge._plugin_to_group_map[pid] = group_id
        bridge._current_count += 1
        return (True, "ok")

    bridge.add_plugin_by_name = Mock(side_effect=add_plugin_side_effect)
    bridge.remove_plugin = Mock(return_value=True)
    bridge.patchbay_connect = Mock(return_value=True)
    bridge.get_audio_port_counts = Mock(return_value=(2, 2))
    bridge.get_plugin_count = Mock(side_effect=lambda: bridge._current_count)

    return bridge


class TestSaveChainPreset:
    def test_saves_preset_file(self, tmp_path):
        bridge = Mock()
        bridge.get_plugin_info = Mock(side_effect=[
            {"name": "Calf EQ"},
            {"name": "Calf Compressor"},
        ])
        bridge.get_all_parameter_details = Mock(side_effect=[
            [
                {"id": 0, "name": "Frequency", "value": 440.0},
                {"id": 1, "name": "Gain", "value": 3.0},
            ],
            [
                {"id": 0, "name": "Threshold", "value": -20.0},
                {"id": 1, "name": "Ratio", "value": 4.0},
            ],
        ])

        with patch("carla_mcp.tools.chain_presets.CHAIN_PRESET_DIR", tmp_path):
            result = save_chain_preset_impl(bridge, "my_preset", [0, 1])

        assert result["success"] is True
        preset_path = tmp_path / "my_preset.json"
        assert preset_path.exists()

        data = json.loads(preset_path.read_text())
        assert data["version"] == 1
        assert data["name"] == "my_preset"
        assert len(data["plugins"]) == 2
        assert data["plugins"][0]["name"] == "Calf EQ"
        assert data["plugins"][0]["parameters"] == {"Frequency": 440.0, "Gain": 3.0}
        assert data["plugins"][1]["name"] == "Calf Compressor"
        assert data["plugins"][1]["parameters"] == {"Threshold": -20.0, "Ratio": 4.0}

    def test_rejects_empty_plugin_list(self):
        bridge = Mock()
        result = save_chain_preset_impl(bridge, "empty", [])
        assert result["success"] is False
        assert "No plugin IDs" in result["error"]

    def test_rejects_invalid_plugin_id(self):
        bridge = Mock()
        bridge.get_plugin_info = Mock(return_value=None)
        result = save_chain_preset_impl(bridge, "bad", [99])
        assert result["success"] is False
        assert "99" in result["error"]


class TestLoadChainPreset:
    @patch("carla_mcp.tools.chain_presets.ensure_carla_to_monitors")
    @patch("carla_mcp.tools.chain_presets.build_chain")
    def test_loads_preset_and_builds_chain(self, mock_build_chain, mock_ensure, tmp_path):
        # Write a preset file
        preset_data = {
            "version": 1,
            "name": "test_preset",
            "plugins": [
                {"name": "Calf EQ", "parameters": {"Frequency": 440.0, "Gain": 3.0}},
                {"name": "Calf Compressor", "parameters": {"Threshold": -20.0}},
            ],
        }
        preset_path = tmp_path / "test_preset.json"
        preset_path.write_text(json.dumps(preset_data))

        # Mock build_chain return
        mock_build_chain.return_value = {
            "success": True,
            "plugins": [
                {"id": 0, "name": "Calf EQ"},
                {"id": 1, "name": "Calf Compressor"},
            ],
            "connections": [{"group_a": 100, "port_a": 510, "group_b": 101, "port_b": 255}],
            "error": None,
        }

        bridge = Mock()
        # For parameter restoration
        bridge.get_all_parameter_details = Mock(side_effect=[
            [{"id": 0, "name": "Frequency", "value": 0.0}, {"id": 1, "name": "Gain", "value": 0.0}],
            [{"id": 0, "name": "Threshold", "value": 0.0}],
        ])
        bridge.set_parameter_value = Mock()

        mock_ensure.return_value = {"connected": 1, "already_connected": 1, "failed": 0}

        with patch("carla_mcp.tools.chain_presets.CHAIN_PRESET_DIR", tmp_path):
            result = load_chain_preset_impl(bridge, "test_preset")

        assert result["success"] is True
        mock_build_chain.assert_called_once_with(
            bridge, ["Calf EQ", "Calf Compressor"], True, True
        )
        # Check params were set
        bridge.set_parameter_value.assert_any_call(0, 0, 440.0)
        bridge.set_parameter_value.assert_any_call(0, 1, 3.0)
        bridge.set_parameter_value.assert_any_call(1, 0, -20.0)

    def test_load_nonexistent_preset(self, tmp_path):
        bridge = Mock()
        with patch("carla_mcp.tools.chain_presets.CHAIN_PRESET_DIR", tmp_path):
            result = load_chain_preset_impl(bridge, "does_not_exist")
        assert result["success"] is False
        assert "not found" in result["error"]


class TestListChainPresets:
    def test_lists_saved_presets(self, tmp_path):
        p1 = {
            "version": 1,
            "name": "preset_a",
            "plugins": [{"name": "EQ", "parameters": {}}],
        }
        p2 = {
            "version": 1,
            "name": "preset_b",
            "plugins": [
                {"name": "Comp", "parameters": {}},
                {"name": "Reverb", "parameters": {}},
            ],
        }
        (tmp_path / "preset_a.json").write_text(json.dumps(p1))
        (tmp_path / "preset_b.json").write_text(json.dumps(p2))

        with patch("carla_mcp.tools.chain_presets.CHAIN_PRESET_DIR", tmp_path):
            result = list_chain_presets_impl()

        assert len(result) == 2
        names = {p["name"] for p in result}
        assert names == {"preset_a", "preset_b"}

        for p in result:
            if p["name"] == "preset_a":
                assert p["plugin_count"] == 1
                assert p["plugins"] == ["EQ"]
            elif p["name"] == "preset_b":
                assert p["plugin_count"] == 2
                assert p["plugins"] == ["Comp", "Reverb"]

    def test_empty_preset_dir(self, tmp_path):
        with patch("carla_mcp.tools.chain_presets.CHAIN_PRESET_DIR", tmp_path):
            result = list_chain_presets_impl()
        assert result == []
