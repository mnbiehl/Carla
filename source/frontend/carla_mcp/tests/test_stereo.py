"""Tests for stereo pair detection and handling."""

import pytest
from carla_mcp.state.stereo import (
    is_stereo_pair,
    get_stereo_pair,
    get_channel_type,
    split_stereo_name,
)


class TestStereoPairDetection:
    """Test detection of stereo pairs from port names."""

    def test_detects_L_R_suffix(self):
        """Detects _L/_R as stereo pair."""
        assert is_stereo_pair("looper:out_1_L", "looper:out_1_R")

    def test_detects_left_right_suffix(self):
        """Detects _left/_right as stereo pair."""
        assert is_stereo_pair("plugin:out_left", "plugin:out_right")

    def test_rejects_non_pair(self):
        """Rejects ports that aren't a stereo pair."""
        assert not is_stereo_pair("looper:out_1_L", "looper:out_2_L")

    def test_get_stereo_pair_from_left(self):
        """Given left port, returns (left, right) tuple."""
        left, right = get_stereo_pair("looper:out_1_L")
        assert left == "looper:out_1_L"
        assert right == "looper:out_1_R"

    def test_get_stereo_pair_from_right(self):
        """Given right port, returns (left, right) tuple."""
        left, right = get_stereo_pair("looper:out_1_R")
        assert left == "looper:out_1_L"
        assert right == "looper:out_1_R"

    def test_get_channel_type_left(self):
        """Identifies left channel."""
        assert get_channel_type("port_L") == "left"
        assert get_channel_type("port_left") == "left"

    def test_get_channel_type_right(self):
        """Identifies right channel."""
        assert get_channel_type("port_R") == "right"
        assert get_channel_type("port_right") == "right"

    def test_get_channel_type_mono(self):
        """Returns mono for non-stereo ports."""
        assert get_channel_type("port_mono") == "mono"
        assert get_channel_type("port") == "mono"

    def test_split_stereo_name(self):
        """Splits stereo port name into base and channel."""
        base, channel = split_stereo_name("looper:out_1_L")
        assert base == "looper:out_1"
        assert channel == "L"
