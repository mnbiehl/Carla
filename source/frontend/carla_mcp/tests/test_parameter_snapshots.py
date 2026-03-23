import json
import pytest
from unittest.mock import MagicMock
from carla_mcp.backend.backend_bridge import CarlaBackendBridge


class TestParameterSnapshots:
    def _make_bridge(self):
        host = MagicMock()
        bridge = CarlaBackendBridge.__new__(CarlaBackendBridge)
        bridge.host = host
        bridge.logger = MagicMock()
        bridge._error_handler = MagicMock()
        bridge._cleanup_performed = True
        return bridge

    def test_save_snapshot(self, tmp_path):
        bridge = self._make_bridge()
        bridge.host.get_parameter_count.return_value = 2
        bridge.host.get_current_parameter_value.side_effect = [0.5, 0.8]

        path = bridge.save_parameter_snapshot(0, "my_snap", snapshot_dir=tmp_path)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data == {"0": 0.5, "1": 0.8}

    def test_load_snapshot(self, tmp_path):
        bridge = self._make_bridge()
        snap_file = tmp_path / "loaded.json"
        snap_file.write_text(json.dumps({"0": 0.3, "1": 0.9}))

        result = bridge.load_parameter_snapshot(7, "loaded", snapshot_dir=tmp_path)

        assert result is True
        bridge.host.set_parameter_value.assert_any_call(7, 0, 0.3)
        bridge.host.set_parameter_value.assert_any_call(7, 1, 0.9)

    def test_load_nonexistent_returns_false(self, tmp_path):
        bridge = self._make_bridge()
        result = bridge.load_parameter_snapshot(0, "no_such_snap", snapshot_dir=tmp_path)
        assert result is False

    def test_save_creates_directory(self, tmp_path):
        bridge = self._make_bridge()
        bridge.host.get_parameter_count.return_value = 1
        bridge.host.get_current_parameter_value.return_value = 0.42

        nested = tmp_path / "sub" / "dir"
        path = bridge.save_parameter_snapshot(0, "nested_snap", snapshot_dir=nested)

        assert nested.exists()
        assert path.exists()
        data = json.loads(path.read_text())
        assert data == {"0": 0.42}
