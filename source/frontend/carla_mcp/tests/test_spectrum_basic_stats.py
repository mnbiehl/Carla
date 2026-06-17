import numpy as np
import pytest
from carla_mcp.tools.spectrum import analyze_wav, AnalyzerOptions
from .fixtures_spectrum import silence, sine, pink_noise


def test_silence_flagged(spectrum_fixtures_dir):
    wav = silence(spectrum_fixtures_dir / "silence.wav", seconds=0.5)
    r = analyze_wav(str(wav))
    assert r["silent"] is True
    assert r["rms_dbfs"] < -60
    assert r["suggestions"] == []


def test_sine_basic_stats(spectrum_fixtures_dir):
    wav = sine(spectrum_fixtures_dir / "sine_1k.wav", freq_hz=1000.0,
               seconds=1.0, amp=0.5)
    r = analyze_wav(str(wav))
    assert r["silent"] is False
    assert r["sample_rate"] == 48000
    assert 0.99 < r["duration_s"] < 1.01
    # 0.5-amplitude sine: RMS = 0.5/sqrt(2) ≈ 0.3536 → -9.0 dBFS
    assert -10 < r["rms_dbfs"] < -8
    assert r["peak_dbfs"] > -7
    # Crest factor of a sine = ~3.01 dB
    assert 2.5 < r["crest_factor_db"] < 3.5


def test_pink_noise_higher_crest(spectrum_fixtures_dir):
    wav = pink_noise(spectrum_fixtures_dir / "pink.wav", seconds=1.0)
    r = analyze_wav(str(wav))
    # Pink noise crest factor is well above a sine's 3 dB
    assert r["crest_factor_db"] > 6
