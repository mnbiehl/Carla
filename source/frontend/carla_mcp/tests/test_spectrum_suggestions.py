from carla_mcp.tools.spectrum import analyze_wav, AnalyzerOptions
from .fixtures_spectrum import pink_noise, pink_plus_resonance, sine


def test_pink_noise_no_strong_suggestions(spectrum_fixtures_dir):
    wav = pink_noise(spectrum_fixtures_dir / "pink_sugg.wav", seconds=2.0)
    r = analyze_wav(str(wav))
    assert len(r["suggestions"]) <= 1
    for s in r["suggestions"]:
        assert s["confidence"] < 0.7


def test_mud_resonance_yields_resonance_notch_or_mud_cut(spectrum_fixtures_dir):
    wav = pink_plus_resonance(spectrum_fixtures_dir / "pink_270_sugg.wav",
                              freq_hz=270.0, q=8.0, seconds=2.0)
    r = analyze_wav(str(wav))
    types = {s["type"] for s in r["suggestions"]}
    assert "resonance_notch" in types or "cut" in types
    in_mud_band = [s for s in r["suggestions"]
                   if 200 <= s["f_hz"] <= 500]
    assert in_mud_band, f"no suggestion in mud zone: {r['suggestions']}"


def test_include_suggestions_false_returns_empty(spectrum_fixtures_dir):
    wav = pink_plus_resonance(spectrum_fixtures_dir / "pink_270_off.wav",
                              freq_hz=270.0, q=8.0, seconds=2.0)
    r = analyze_wav(str(wav), AnalyzerOptions(include_suggestions=False))
    assert r["suggestions"] == []
