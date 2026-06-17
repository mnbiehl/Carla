import pytest
from carla_mcp.tools.spectrum import analyze_wav
from .fixtures_spectrum import sine, pink_noise


def test_erb_bands_populated(spectrum_fixtures_dir):
    wav = pink_noise(spectrum_fixtures_dir / "pink_erb.wav", seconds=1.0)
    r = analyze_wav(str(wav))
    bands = r["erb_bands"]
    assert 30 <= len(bands) <= 50, f"expected ~40 ERB bands, got {len(bands)}"
    centers = [b["f_center_hz"] for b in bands]
    assert centers == sorted(centers)
    for b in bands:
        assert "rms_db" in b
        assert -200 < b["rms_db"] < 50


def test_erb_band_locates_sine_peak(spectrum_fixtures_dir):
    wav = sine(spectrum_fixtures_dir / "sine_2k.wav", freq_hz=2000.0,
               seconds=1.0, amp=0.5)
    r = analyze_wav(str(wav))
    bands = r["erb_bands"]
    top = max(bands, key=lambda b: b["rms_db"])
    assert 1500 <= top["f_center_hz"] <= 2700
