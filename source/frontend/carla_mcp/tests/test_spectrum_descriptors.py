from carla_mcp.tools.spectrum import analyze_wav
from .fixtures_spectrum import sine, pink_noise


def test_centroid_matches_sine_freq(spectrum_fixtures_dir):
    wav = sine(spectrum_fixtures_dir / "sine_3k.wav", freq_hz=3000.0,
               seconds=1.0, amp=0.5)
    r = analyze_wav(str(wav))
    assert 2700 <= r["centroid_hz"] <= 3300


def test_pink_descriptors_reasonable(spectrum_fixtures_dir):
    wav = pink_noise(spectrum_fixtures_dir / "pink_desc.wav", seconds=2.0)
    r = analyze_wav(str(wav))
    assert 200 < r["centroid_hz"] < 6000
    assert r["rolloff_95_hz"] > r["rolloff_85_hz"] > r["centroid_hz"]
    assert 0.0 < r["flatness"] < 1.0
    assert r["bandwidth_hz"] > 0
