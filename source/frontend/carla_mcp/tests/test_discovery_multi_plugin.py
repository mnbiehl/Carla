"""
Tests for multi-plugin bundle discovery parsing.

When carla-discovery-native processes an LV2 bundle containing multiple plugins
(e.g., lsp-plugins.lv2), it outputs all of them separated by init markers.
The parser must split and return each plugin individually.
"""

import pytest
from unittest.mock import patch, MagicMock
from ..discovery.carla_discovery_parser import CarlaDiscoveryParser, PluginInfo


# Sample multi-plugin discovery output (3 plugins)
MULTI_PLUGIN_OUTPUT = """\
carla-discovery::init::-----------
carla-discovery::build::2
carla-discovery::name::LSP Compressor Mono
carla-discovery::maker::LSP LV2
carla-discovery::label::http://lsp-plug.in/plugins/lv2/compressor_mono
carla-discovery::audio.ins::1
carla-discovery::audio.outs::1
carla-discovery::midi.ins::0
carla-discovery::midi.outs::0
carla-discovery::parameters.ins::10
carla-discovery::parameters.outs::5
carla-discovery::end::
carla-discovery::init::-----------
carla-discovery::build::2
carla-discovery::name::LSP Compressor Stereo
carla-discovery::maker::LSP LV2
carla-discovery::label::http://lsp-plug.in/plugins/lv2/compressor_stereo
carla-discovery::audio.ins::2
carla-discovery::audio.outs::2
carla-discovery::midi.ins::0
carla-discovery::midi.outs::0
carla-discovery::parameters.ins::20
carla-discovery::parameters.outs::10
carla-discovery::end::
carla-discovery::init::-----------
carla-discovery::build::2
carla-discovery::name::LSP Limiter Mono
carla-discovery::maker::LSP LV2
carla-discovery::label::http://lsp-plug.in/plugins/lv2/limiter_mono
carla-discovery::audio.ins::1
carla-discovery::audio.outs::1
carla-discovery::midi.ins::0
carla-discovery::midi.outs::0
carla-discovery::parameters.ins::8
carla-discovery::parameters.outs::4
carla-discovery::end::
"""


class TestMultiPluginParsing:
    """Tests for _parse_discovery_output_multi and discover_plugins"""

    def setup_method(self):
        self.parser = CarlaDiscoveryParser()

    def test_parse_returns_list_of_all_plugins(self):
        """3 plugins in output should produce 3 PluginInfo objects."""
        results = self.parser._parse_discovery_output_multi(
            MULTI_PLUGIN_OUTPUT, "lv2", "/usr/lib/lv2/lsp-plugins.lv2"
        )
        assert len(results) == 3
        names = [p.name for p in results]
        assert "LSP Compressor Mono" in names
        assert "LSP Compressor Stereo" in names
        assert "LSP Limiter Mono" in names

    def test_mono_plugin_has_correct_port_counts(self):
        """First plugin (Compressor Mono) should have 1 audio in, 1 audio out."""
        results = self.parser._parse_discovery_output_multi(
            MULTI_PLUGIN_OUTPUT, "lv2", "/usr/lib/lv2/lsp-plugins.lv2"
        )
        mono = [p for p in results if p.name == "LSP Compressor Mono"][0]
        assert mono.audio_ins == 1
        assert mono.audio_outs == 1

    def test_stereo_plugin_has_correct_port_counts(self):
        """Second plugin (Compressor Stereo) should have 2 audio in, 2 audio out."""
        results = self.parser._parse_discovery_output_multi(
            MULTI_PLUGIN_OUTPUT, "lv2", "/usr/lib/lv2/lsp-plugins.lv2"
        )
        stereo = [p for p in results if p.name == "LSP Compressor Stereo"][0]
        assert stereo.audio_ins == 2
        assert stereo.audio_outs == 2

    def test_discover_plugin_singular_still_works(self):
        """Backward compat: discover_plugin returns a single PluginInfo."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = MULTI_PLUGIN_OUTPUT

        with patch("subprocess.run", return_value=mock_result):
            result = self.parser.discover_plugin("lv2", "/usr/lib/lv2/lsp-plugins.lv2")

        assert isinstance(result, PluginInfo)
        assert result.name == "LSP Compressor Mono"

    def test_discover_plugins_returns_all_from_bundle(self):
        """discover_plugins (plural) should return all plugins from a bundle."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = MULTI_PLUGIN_OUTPUT

        with patch("subprocess.run", return_value=mock_result):
            results = self.parser.discover_plugins("lv2", "/usr/lib/lv2/lsp-plugins.lv2")

        assert isinstance(results, list)
        assert len(results) == 3
        assert all(isinstance(p, PluginInfo) for p in results)

    def test_single_plugin_output_still_works(self):
        """A single-plugin output should return a list with one element."""
        single_output = """\
carla-discovery::init::-----------
carla-discovery::build::2
carla-discovery::name::My Plugin
carla-discovery::maker::Test
carla-discovery::label::http://example.com/plugin
carla-discovery::audio.ins::2
carla-discovery::audio.outs::2
carla-discovery::end::
"""
        results = self.parser._parse_discovery_output_multi(
            single_output, "lv2", "/usr/lib/lv2/test.lv2"
        )
        assert len(results) == 1
        assert results[0].name == "My Plugin"

    def test_empty_output_returns_empty_list(self):
        """Empty output should return an empty list."""
        results = self.parser._parse_discovery_output_multi(
            "", "lv2", "/usr/lib/lv2/test.lv2"
        )
        assert results == []
