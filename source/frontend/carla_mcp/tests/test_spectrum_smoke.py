def test_module_imports():
    from carla_mcp.tools import spectrum
    assert hasattr(spectrum, "AnalyzerOptions")
    assert hasattr(spectrum, "SpectrumReport")
    assert hasattr(spectrum, "analyze_wav")
    assert hasattr(spectrum, "capture_port")
    assert hasattr(spectrum, "analyze_port")
    assert hasattr(spectrum, "register_spectrum_tools")
