from carla_mcp.tools.spectrum import analyze_wav, AnalyzerOptions
from .fixtures_spectrum import sine, pink_noise, pink_plus_resonance


def test_sine_creates_one_dominant_resonance(spectrum_fixtures_dir):
    wav = sine(spectrum_fixtures_dir / "sine_1500.wav", freq_hz=1500.0,
               seconds=1.0, amp=0.5)
    r = analyze_wav(str(wav))
    res = r["resonances"]
    assert len(res) >= 1
    top = max(res, key=lambda d: d["prominence_db"])
    assert 1350 <= top["f_hz"] <= 1650
    assert top["prominence_db"] > 20
    assert top["persistence"] > 0.9


def test_pink_noise_yields_few_resonances(spectrum_fixtures_dir):
    wav = pink_noise(spectrum_fixtures_dir / "pink_res.wav", seconds=2.0)
    r = analyze_wav(str(wav), AnalyzerOptions(resonance_min_prominence_db=8.0,
                                              resonance_min_persistence=0.6))
    assert len(r["resonances"]) <= 4


def test_pink_plus_resonance_finds_injected_peak(spectrum_fixtures_dir):
    wav = pink_plus_resonance(spectrum_fixtures_dir / "pink_320.wav",
                              freq_hz=320.0, q=12.0, seconds=2.0)
    r = analyze_wav(str(wav))
    assert any(280 <= d["f_hz"] <= 360 for d in r["resonances"]), \
        f"injected 320 Hz resonance not detected: {r['resonances']}"
