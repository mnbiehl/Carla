import pytest
from carla_mcp.tools.spectrum import AnalyzerOptions


def test_weighting_uppercase_normalized():
    opts = AnalyzerOptions(weighting="A")
    assert opts.weighting == "a"


def test_weighting_with_whitespace_normalized():
    opts = AnalyzerOptions(weighting="  none  ")
    assert opts.weighting == "none"


def test_weighting_unknown_raises():
    with pytest.raises(ValueError, match="weighting"):
        AnalyzerOptions(weighting="foo")


def test_weighting_default_is_a():
    assert AnalyzerOptions().weighting == "a"
