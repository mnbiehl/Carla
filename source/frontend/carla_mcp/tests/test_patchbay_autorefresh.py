"""Tests that patchbay is auto-refreshed after plugin add/remove."""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock


@pytest.fixture
def bridge():
    """Create a CarlaBackendBridge with a mocked host."""
    with patch("carla_mcp.backend.backend_bridge.get_error_handler"):
        from carla_mcp.backend.backend_bridge import CarlaBackendBridge
        b = CarlaBackendBridge.__new__(CarlaBackendBridge)
        b.host = MagicMock()
        b.logger = MagicMock()
        b._engine_running = True
        b._cleanup_performed = False
        return b


def test_add_plugin_by_name_refreshes_patchbay(bridge):
    """patchbay_refresh must be called after a successful plugin add."""
    fake_plugin_info = {
        "name": "TestPlugin",
        "plugin_type": "lv2",
        "label": "http://example.org/test",
        "filename": "",
    }

    fake_result = MagicMock()
    fake_result.name = "TestPlugin"
    fake_result.plugin_type = "lv2"
    fake_result.to_dict.return_value = fake_plugin_info

    fake_db = MagicMock()
    fake_db.search_plugins.return_value = [fake_result]

    fake_discoverer = MagicMock()
    fake_discoverer.get_database.return_value = fake_db

    with patch(
        "carla_mcp.backend.backend_bridge.CarlaBackendBridge._add_plugin_from_database",
        return_value=(True, "Plugin added"),
    ) as mock_add, patch(
        "carla_mcp.discovery.plugin_discoverer.PluginDiscoverer",
        return_value=fake_discoverer,
    ):
        success, msg = bridge.add_plugin_by_name("TestPlugin")

    assert success is True
    bridge.host.patchbay_refresh.assert_called_once_with(False)


def test_remove_plugin_refreshes_patchbay(bridge):
    """patchbay_refresh must be called after a successful plugin remove."""
    bridge.host.remove_plugin.return_value = True

    result = bridge.remove_plugin(0)

    assert result is True
    bridge.host.patchbay_refresh.assert_called_once_with(False)


def test_failed_add_does_not_refresh(bridge):
    """patchbay_refresh must NOT be called if plugin add fails."""
    fake_result = MagicMock()
    fake_result.name = "TestPlugin"
    fake_result.plugin_type = "lv2"
    fake_result.to_dict.return_value = {
        "name": "TestPlugin",
        "plugin_type": "lv2",
        "label": "http://example.org/test",
        "filename": "",
    }

    fake_db = MagicMock()
    fake_db.search_plugins.return_value = [fake_result]

    fake_discoverer = MagicMock()
    fake_discoverer.get_database.return_value = fake_db

    with patch(
        "carla_mcp.backend.backend_bridge.CarlaBackendBridge._add_plugin_from_database",
        return_value=(False, "Failed to add"),
    ), patch(
        "carla_mcp.discovery.plugin_discoverer.PluginDiscoverer",
        return_value=fake_discoverer,
    ):
        success, msg = bridge.add_plugin_by_name("TestPlugin")

    assert success is False
    bridge.host.patchbay_refresh.assert_not_called()
