import numpy as np
from carla_mcp.tools.spectrum import analyze_wav
from .fixtures_spectrum import pink_noise, sine


def test_pink_noise_close_to_zero_diff(spectrum_fixtures_dir):
    wav = pink_noise(spectrum_fixtures_dir / "pink_long.wav", seconds=2.0)
    r = analyze_wav(str(wav))
    diffs = np.array(r["pink_diff_db"])
    interior = diffs[3:-3]  # drop edge bands where filterbank smearing dominates
    assert np.all(np.abs(interior) < 6), \
        f"interior pink_diff too large: {interior}"


def test_sine_has_strong_positive_diff_at_peak(spectrum_fixtures_dir):
    wav = sine(spectrum_fixtures_dir / "sine_500.wav", freq_hz=500.0,
               seconds=1.0, amp=0.5)
    r = analyze_wav(str(wav))
    diffs = np.array(r["pink_diff_db"])
    centers = np.array([b["f_center_hz"] for b in r["erb_bands"]])
    peak_band = int(np.argmax(diffs))
    assert 350 <= centers[peak_band] <= 700
    assert diffs[peak_band] > 20
