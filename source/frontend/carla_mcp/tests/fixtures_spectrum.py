"""Synthetic WAV generators for spectrum analyzer tests."""
from __future__ import annotations
import numpy as np
import soundfile as sf
from pathlib import Path

SR = 48000


def _write(path: Path, x: np.ndarray, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, x.astype(np.float32), sr, subtype="FLOAT")
    return path


def silence(path: Path, seconds: float = 1.0) -> Path:
    return _write(path, np.zeros(int(seconds * SR)))


def sine(path: Path, freq_hz: float, seconds: float = 1.0, amp: float = 0.5) -> Path:
    t = np.arange(int(seconds * SR)) / SR
    return _write(path, amp * np.sin(2 * np.pi * freq_hz * t))


def _pink_array(n: int, seed: int, amp: float) -> np.ndarray:
    """Pink noise samples via 1/sqrt(f) spectral shaping of Gaussian white."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n)
    spec = np.fft.rfft(white)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    f[0] = 1.0
    spec = spec / np.sqrt(f)
    pink = np.fft.irfft(spec, n=n)
    return pink / (np.max(np.abs(pink)) + 1e-12) * amp


def pink_noise(path: Path, seconds: float = 2.0, seed: int = 0, amp: float = 0.3) -> Path:
    """Pink noise via 1/sqrt(f) spectral shaping of Gaussian white."""
    return _write(path, _pink_array(int(seconds * SR), seed, amp))


def pink_plus_resonance(path: Path, freq_hz: float, q: float = 8.0,
                       seconds: float = 2.0, seed: int = 0) -> Path:
    """Pink noise with an added narrow-band resonance at freq_hz."""
    assert 0 < freq_hz < SR / 2, f"freq_hz must be in (0, {SR/2}); got {freq_hz}"
    from scipy.signal import iirpeak, lfilter
    x = _pink_array(int(seconds * SR), seed, 0.3)
    b, a = iirpeak(freq_hz / (SR / 2), q)
    boosted = lfilter(b, a, x) * 4.0
    out = x + boosted
    return _write(path, out / (np.max(np.abs(out)) + 1e-12) * 0.7)
