"""Regression tests for LV2 URI split handling.

When an LV2 label like 'lsp-plugins.lv2/http://lsp-plug.in/plugins/lv2/compressor_mono'
is passed, the code must split on the first '/' only so the full URI
'http://lsp-plug.in/plugins/lv2/compressor_mono' is preserved as the label.
"""

import pytest
from unittest.mock import MagicMock, patch

from carla_mcp.backend.backend_bridge import CarlaBackendBridge


@pytest.fixture
def bridge():
    """Create a bridge with a mock host."""
    host = MagicMock()
    host.is_engine_running.return_value = True
    host.add_plugin.return_value = True
    host.get_last_error.return_value = ""
    host.patchbay_refresh = MagicMock()
    b = CarlaBackendBridge(host)
    return b


class TestAddPluginLV2UriSplit:
    """Tests for add_plugin() LV2 URI handling."""

    def test_add_plugin_lv2_preserves_full_uri(self, bridge):
        """Label with bundle/URI should pass the full URI to host.add_plugin."""
        label = "lsp-plugins.lv2/http://lsp-plug.in/plugins/lv2/compressor_mono"

        bridge.add_plugin(plugin_type="lv2", filename="", name="", label=label)

        call_args = bridge.host.add_plugin.call_args
        # label is the 5th positional arg (index 4)
        actual_label = call_args[0][4]
        assert actual_label == "http://lsp-plug.in/plugins/lv2/compressor_mono"

    def test_add_plugin_lv2_no_slash_passes_through(self, bridge):
        """Label without '/' passes through unchanged."""
        label = "urn:simple-plugin"

        bridge.add_plugin(plugin_type="lv2", filename="", name="", label=label)

        call_args = bridge.host.add_plugin.call_args
        actual_label = call_args[0][4]
        assert actual_label == "urn:simple-plugin"


class TestAddPluginFromDatabaseLV2UriSplit:
    """Tests for _add_plugin_from_database() LV2 URI handling."""

    def test_add_plugin_from_database_preserves_uri(self, bridge):
        """Database plugin info with bundle/URI label should preserve full URI."""
        plugin_info = {
            "name": "LSP Compressor Mono",
            "plugin_type": "lv2",
            "label": "lsp-plugins.lv2/http://lsp-plug.in/plugins/lv2/compressor_mono",
            "type": 4,  # PLUGIN_LV2
            "uniqueId": 0,
            "build": 2,  # BINARY_POSIX64
            "filename": "/some/path",
        }

        bridge._add_plugin_from_database(plugin_info)

        call_args = bridge.host.add_plugin.call_args
        # In _add_plugin_from_database: host.add_plugin(build_type, plugin_type, filename, None, label, ...)
        actual_filename = call_args[0][2]
        actual_label = call_args[0][4]
        assert actual_filename == ""
        assert actual_label == "http://lsp-plug.in/plugins/lv2/compressor_mono"

    def test_add_plugin_from_database_no_slash_label(self, bridge):
        """Database LV2 plugin with no '/' in label passes through."""
        plugin_info = {
            "name": "Simple Plugin",
            "plugin_type": "lv2",
            "label": "urn:simple",
            "type": 4,
            "uniqueId": 0,
            "build": 2,
        }

        bridge._add_plugin_from_database(plugin_info)

        call_args = bridge.host.add_plugin.call_args
        actual_label = call_args[0][4]
        assert actual_label == "urn:simple"
