from carla_mcp.tools.spectrum import analyze_wav, AnalyzerOptions
from .fixtures_spectrum import sine


def test_a_weighting_attenuates_low_freqs(spectrum_fixtures_dir):
    """A-weight value of a 100 Hz tone should be ~19 dB below an equivalent
    1 kHz tone (A(100) ≈ -19, A(1000) ≈ 0)."""
    low = sine(spectrum_fixtures_dir / "sine_100.wav", freq_hz=100.0, amp=0.5)
    mid = sine(spectrum_fixtures_dir / "sine_1k_w.wav", freq_hz=1000.0, amp=0.5)

    rl = analyze_wav(str(low), AnalyzerOptions(weighting="a"))
    rm = analyze_wav(str(mid), AnalyzerOptions(weighting="a"))

    def top_band(r):
        return max(r["erb_bands"], key=lambda b: b["rms_db"])

    bl = top_band(rl)
    bm = top_band(rm)
    delta = (bl["rms_db_a_weighted"] - bl["rms_db"]) - \
            (bm["rms_db_a_weighted"] - bm["rms_db"])
    assert -22 < delta < -16, (
        f"100 Hz should be ~19 dB below 1 kHz under A-weighting, got {delta}"
    )


def test_no_weighting_leaves_band_values_equal(spectrum_fixtures_dir):
    """With weighting='none', rms_db_a_weighted should equal rms_db."""
    wav = sine(spectrum_fixtures_dir / "sine_500_none.wav", freq_hz=500.0, amp=0.5)
    r = analyze_wav(str(wav), AnalyzerOptions(weighting="none"))
    for b in r["erb_bands"]:
        assert abs(b["rms_db_a_weighted"] - b["rms_db"]) < 1e-6


def test_iso226_falls_back_with_warning(spectrum_fixtures_dir, caplog, monkeypatch):
    """ISO 226 weighting is deferred — should fall back to no weighting and warn."""
    import logging
    from carla_mcp.tools import spectrum as spectrum_mod
    monkeypatch.setattr(spectrum_mod, "_iso226_warned", False)
    caplog.set_level(logging.WARNING)
    wav = sine(spectrum_fixtures_dir / "sine_500_iso.wav", freq_hz=500.0, amp=0.5)
    r = analyze_wav(str(wav), AnalyzerOptions(weighting="iso226"))
    for b in r["erb_bands"]:
        assert abs(b["rms_db_a_weighted"] - b["rms_db"]) < 1e-6
    assert any("iso226" in rec.getMessage().lower() for rec in caplog.records), \
        "expected a warning about iso226 fallback"
