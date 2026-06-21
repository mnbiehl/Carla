"""Spectrum-driven analysis tools for assistant-led EQ tuning.

See kb/Carla/design-docs/spectrum-driven-analysis-for-assistant-led-eq-tuning.md
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal, Optional
import logging
import subprocess
import tempfile
import time

import librosa
import numpy as np
import soundfile as sf
from gammatone.filters import make_erb_filters, centre_freqs, erb_filterbank
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks, peak_widths

from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge


_log = logging.getLogger(__name__)
_iso226_warned = False

_SILENT_THRESHOLD_DBFS = -60.0

_DEFAULT_TMP_ROOT = Path(tempfile.gettempdir()) / "carla-mcp-spectrum"


def _default_capture_path() -> Path:
    _DEFAULT_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_TMP_ROOT / f"capture-{int(time.time() * 1000)}.wav"


def _validate_output_path(output_path: Optional[str]) -> Path:
    """Resolve the requested output path, restricting it to _DEFAULT_TMP_ROOT.

    Raises ValueError on traversal, symlinks, or overwrite of an existing
    non-tmp file."""
    if output_path is None:
        return _default_capture_path()
    p = Path(output_path).expanduser().resolve(strict=False)
    root = _DEFAULT_TMP_ROOT.resolve(strict=False)
    try:
        p.relative_to(root)
    except ValueError:
        raise ValueError(
            f"output_path must be under {root}; got {p}"
        )
    if p.is_symlink():
        raise ValueError(f"output_path must not be a symlink: {p}")
    if p.exists() and not p.is_file():
        raise ValueError(f"output_path exists and is not a regular file: {p}")
    return p


@dataclass
class AnalyzerOptions:
    fft_size: int = 8192
    window: str = "hann"
    hop: int = 2048
    weighting: Literal["none", "a", "iso226"] = "a"
    pink_reference_hz: float = 1000.0
    resonance_min_prominence_db: float = 6.0
    resonance_min_persistence: float = 0.5
    include_suggestions: bool = True

    def __post_init__(self):
        if isinstance(self.weighting, str):
            self.weighting = self.weighting.strip().lower()
        valid = {"none", "a", "iso226"}
        if self.weighting not in valid:
            raise ValueError(
                f"weighting must be one of {sorted(valid)}; got {self.weighting!r}"
            )


@dataclass
class SpectrumReport:
    sample_rate: int
    duration_s: float
    rms_dbfs: float
    peak_dbfs: float
    crest_factor_db: float
    silent: bool = False
    erb_bands: list[dict] = field(default_factory=list)
    pink_diff_db: list[float] = field(default_factory=list)
    centroid_hz: float = 0.0
    rolloff_85_hz: float = 0.0
    rolloff_95_hz: float = 0.0
    flatness: float = 0.0
    bandwidth_hz: float = 0.0
    resonances: list[dict] = field(default_factory=list)
    zones: dict[str, dict] = field(default_factory=dict)
    suggestions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_mono(x: np.ndarray) -> np.ndarray:
    return x if x.ndim == 1 else x.mean(axis=1)


def _db(x: float) -> float:
    return 20.0 * np.log10(max(float(x), 1e-12))


def _erb_band_energies(x: np.ndarray, sr: int, num_bands: int = 40,
                       low_hz: float = 30.0):
    """Return (centers_hz, rms_db_per_band) using a gammatone ERB filterbank."""
    centers = centre_freqs(sr, num_bands, low_hz)  # high->low order
    coefs = make_erb_filters(sr, centers)
    bank = erb_filterbank(x, coefs)               # shape (num_bands, n_samples)
    rms = np.sqrt(np.mean(bank ** 2, axis=1) + 1e-24)
    rms_db = 20.0 * np.log10(rms)
    centers = centers[::-1]
    rms_db = rms_db[::-1]
    return centers, rms_db


def _a_weight_db(f_hz: np.ndarray) -> np.ndarray:
    """IEC 61672 A-weighting curve, dB. Vectorized over frequency.

    Normalized so A(1 kHz) = 0 dB (the customary +2.00 dB offset is applied)."""
    f = np.asarray(f_hz, dtype=np.float64)
    f2 = f * f
    num = (12194.0 ** 2) * (f2 ** 2)
    den = (f2 + 20.6 ** 2) * \
          np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * \
          (f2 + 12194.0 ** 2)
    ra = num / den
    return 20.0 * np.log10(ra + 1e-24) + 2.00


def _erb_bandwidth_hz(centers_hz: np.ndarray) -> np.ndarray:
    """Glasberg & Moore (1990) ERB bandwidth approximation in Hz."""
    return 24.7 + 0.108 * np.asarray(centers_hz, dtype=np.float64)


def _pink_target_db(centers_hz: np.ndarray, ref_hz: float) -> np.ndarray:
    """Expected ERB-band level (dB) for ideal pink noise (1/f power density).

    Pink-noise band power scales as ERB(fc)/fc, giving an effective slope of
    roughly -3 dB/octave at high fc (where ERB ~= 0.108*fc) and shallower at
    low fc (where the additive 24.7 Hz term dominates). Anchored so the band
    nearest ref_hz reads 0.
    """
    centers = np.clip(np.asarray(centers_hz, dtype=np.float64), 1.0, None)
    erb_bw = _erb_bandwidth_hz(centers)
    raw = 10.0 * np.log10(erb_bw / centers)
    ref_idx = int(np.argmin(np.abs(centers - ref_hz)))
    return raw - raw[ref_idx]


def _pink_diff(centers_hz: np.ndarray, rms_db: np.ndarray,
               ref_hz: float) -> np.ndarray:
    """Per-band signed dB above (+) or below (-) pink slope, normalized so the
    band closest to ref_hz reads 0."""
    target = _pink_target_db(centers_hz, ref_hz)
    raw_diff = rms_db - target
    ref_idx = int(np.argmin(np.abs(centers_hz - ref_hz)))
    return raw_diff - raw_diff[ref_idx]


def _spectral_descriptors(x: np.ndarray, sr: int, options: AnalyzerOptions):
    n_fft = options.fft_size
    hop = options.hop
    S = np.abs(librosa.stft(x.astype(np.float32), n_fft=n_fft, hop_length=hop,
                             window=options.window))
    # Use power spectrum so descriptors are energy-weighted (matches
    # acoustical conventions and fixture-test expectations for pink noise).
    P = S ** 2
    centroid = float(np.mean(librosa.feature.spectral_centroid(S=P, sr=sr)))
    roll85 = float(np.mean(librosa.feature.spectral_rolloff(
        S=P, sr=sr, roll_percent=0.85)))
    roll95 = float(np.mean(librosa.feature.spectral_rolloff(
        S=P, sr=sr, roll_percent=0.95)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(S=P, power=1.0)))
    bw = float(np.mean(librosa.feature.spectral_bandwidth(S=P, sr=sr)))
    return centroid, roll85, roll95, flatness, bw


ZONE_DEFS = {
    "sub":       (20.0,    60.0),
    "low":       (60.0,    200.0),
    "mud":       (200.0,   500.0),
    "boxiness":  (400.0,   800.0),
    "presence":  (1000.0,  4000.0),
    "harshness": (2000.0,  5000.0),
    "sibilance": (5000.0,  10000.0),
    "air":       (10000.0, 20000.0),
}


def _zones_from_bands(erb_bands: list[dict], pink_diff_db: list[float]
                     ) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, (lo, hi) in ZONE_DEFS.items():
        idxs = [i for i, b in enumerate(erb_bands)
                if b["f_center_hz"] >= lo and b["f_center_hz"] < hi]
        if not idxs:
            out[name] = {"f_lo": lo, "f_hi": hi, "rms_db": -120.0, "vs_pink_db": 0.0}
            continue
        rms = float(np.mean([erb_bands[i]["rms_db"] for i in idxs]))
        vs_pink = float(np.mean([pink_diff_db[i] for i in idxs]))
        out[name] = {"f_lo": lo, "f_hi": hi, "rms_db": rms, "vs_pink_db": vs_pink}
    return out


def _erb_edges(centers: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Approximate band edges as midpoints between adjacent centers."""
    mids = (centers[:-1] + centers[1:]) / 2.0
    f_lo = np.concatenate(([centers[0] * 0.5], mids))
    f_hi = np.concatenate((mids, [centers[-1] * 1.5]))
    return f_lo, f_hi


def _detect_resonances(x: np.ndarray, sr: int, options: AnalyzerOptions) -> list[dict]:
    """Detect prominent, persistent spectral peaks across STFT frames.

    Two-stage soothe2/RESO-style: candidates from time-averaged residual
    spectrum, persistence + Q from per-frame check. See comment below for
    why this differs from the plan's per-frame-find_peaks formulation.

    Two-stage approach (soothe2/RESO style):
      1) Locate candidate resonance frequencies as peaks of the *time-averaged*
         residual spectrum (raw STFT magnitude minus a smoothed envelope).
         Averaging suppresses broadband noise's incidental spectral bumps.
      2) For each candidate, measure persistence = fraction of STFT frames in
         which a local maximum occurs at the same FFT bin (within a small
         tolerance), and estimate Q from the -3 dB width of the *averaged*
         peak.

    Returns a list (descending by prominence) of dicts with:
      f_hz, magnitude_db, prominence_db, q_estimate, persistence (0..1)
    """
    n_fft = options.fft_size
    hop = options.hop
    S = np.abs(librosa.stft(x.astype(np.float32), n_fft=n_fft, hop_length=hop,
                             window=options.window))
    n_freq, n_frames = S.shape
    if n_frames == 0:
        return []

    # Plan literally specified per-frame find_peaks-then-aggregate. That was
    # unworkable: (a) Q=12 resonances drift between adjacent FFT bins so
    # exact-bin persistence undercounts; (b) a single pink-noise realization
    # has fixed spectral fine-structure that produces persistent peaks at
    # 16-18 dB prominence, yielding ~16 spurious "resonances" where the
    # design wants <= 4. Two-stage approach (closer to soothe2/RESO):
    # (1) locate candidates as peaks in the residual = time-averaged STFT
    #     magnitude minus its boxcar-smoothed envelope (~500 Hz window);
    # (2) for each candidate, persistence = fraction of frames with a local
    #     max within +/- tol_bins; q estimated from -3 dB width on the
    #     averaged spectrum.
    # Q-from-residual systematically under-estimates true acoustic Q (broad
    # context is removed) -- acceptable for ranking; downstream EQ
    # suggestion code should treat q_estimate as a relative shape hint.
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    bin_hz = sr / n_fft

    # Time-averaged magnitude spectrum (in dB), and a smoothed envelope as
    # the local baseline. Peaks above this baseline are resonance candidates.
    S_db = librosa.amplitude_to_db(S + 1e-12)
    avg_db = librosa.amplitude_to_db(S.mean(axis=1) + 1e-12)
    smooth_bins = max(9, int(round(500.0 / bin_hz)))  # ~500 Hz baseline
    if smooth_bins % 2 == 0:
        smooth_bins += 1
    avg_smooth = uniform_filter1d(avg_db, size=smooth_bins, mode="reflect")
    avg_resid = avg_db - avg_smooth

    peaks, props = find_peaks(avg_resid,
                              prominence=options.resonance_min_prominence_db,
                              distance=3)
    if len(peaks) == 0:
        return []
    widths_samples, _, _, _ = peak_widths(avg_resid, peaks, rel_height=0.5)

    # Only count frames where a local maximum exists within `tol_bins` of the
    # candidate bin, so a slightly drifting peak still counts as persistent.
    tol_bins = 4

    out: list[dict] = []
    for p, prom, w_samp in zip(peaks, props["prominences"], widths_samples):
        f_hz = float(freqs[p])
        if f_hz < 30 or f_hz > sr * 0.45:
            continue
        # Persistence: fraction of frames with a local-max within tolerance.
        lo = max(1, p - tol_bins)
        hi = min(n_freq - 1, p + tol_bins)
        hits = 0
        for f_idx in range(n_frames):
            col = S_db[:, f_idx]
            local_max = lo + int(np.argmax(col[lo:hi + 1]))
            left = col[max(local_max - 1, 0)]
            right = col[min(local_max + 1, n_freq - 1)]
            if col[local_max] > left and col[local_max] > right:
                hits += 1
        persistence = hits / n_frames
        if persistence < options.resonance_min_persistence:
            continue
        width_hz = float(max(w_samp * bin_hz, 1.0))
        q_est = f_hz / width_hz if width_hz > 0 else 0.0
        mag_db = float(avg_db[p])
        out.append({"f_hz": f_hz, "magnitude_db": mag_db,
                    "prominence_db": float(prom),
                    "q_estimate": float(q_est),
                    "persistence": float(persistence)})
    out.sort(key=lambda d: -d["prominence_db"])
    return out[:16]


_MUD_VS_PINK_THRESHOLD = 3.0
_HARSH_VS_PINK_THRESHOLD = 4.0
_SUB_VS_PINK_THRESHOLD = 3.0
_AIR_BELOW_PINK_THRESHOLD = -6.0
# Suggestion-level resonance gates are stricter than the detector-level gates
# in AnalyzerOptions: a single pink-noise realization has fixed spectral
# fine-structure that produces ~6 dB-prominence "peaks" with high persistence.
# A real Q=8 boosted resonance reads ~8+ dB prominence, so 7 dB cleanly
# separates intentional resonances from noise artifacts at the rules layer.
_RESONANCE_PROM_THRESHOLD = 7.0
_RESONANCE_PERSIST_THRESHOLD = 0.5


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _build_suggestions(report: SpectrumReport) -> list[dict]:
    suggestions: list[dict] = []
    z = report.zones
    res = report.resonances

    # Resonance notches first
    for r in res:
        if (r["prominence_db"] >= _RESONANCE_PROM_THRESHOLD
                and r["persistence"] >= _RESONANCE_PERSIST_THRESHOLD):
            q = r["q_estimate"] if r["q_estimate"] > 0.5 else 4.0
            suggestions.append({
                "type": "resonance_notch",
                "f_hz": float(r["f_hz"]),
                "q": float(_clip(q, 1.0, 12.0)),
                "gain_db": float(-min(r["prominence_db"], 9.0)),
                "reason": f"resonance at {int(r['f_hz'])} Hz, "
                          f"{r['prominence_db']:.1f} dB prominence, "
                          f"{r['persistence']*100:.0f}% persistence",
                "evidence": {"prominence_db": r["prominence_db"],
                             "persistence": r["persistence"]},
                "confidence": float(_clip(r["persistence"], 0.5, 0.95)),
            })

    has_mud_resonance = any(200 <= r["f_hz"] <= 500 for r in res
                            if r["prominence_db"] >= _RESONANCE_PROM_THRESHOLD)

    mud_v = z.get("mud", {}).get("vs_pink_db", 0.0)
    if mud_v > _MUD_VS_PINK_THRESHOLD and not has_mud_resonance:
        suggestions.append({
            "type": "cut",
            "f_hz": 300.0,
            "q": 0.7,
            "gain_db": -float(_clip(mud_v - 3.0, 1.0, 6.0)),
            "reason": f"mud zone {mud_v:+.1f} dB vs pink reference",
            "evidence": {"vs_pink_db": mud_v},
            "confidence": 0.6,
        })

    harsh_v = z.get("harshness", {}).get("vs_pink_db", 0.0)
    if harsh_v > _HARSH_VS_PINK_THRESHOLD:
        suggestions.append({
            "type": "cut",
            "f_hz": 3500.0,
            "q": 1.0,
            "gain_db": -float(_clip(harsh_v - 3.0, 1.0, 5.0)),
            "reason": f"harshness zone {harsh_v:+.1f} dB vs pink reference",
            "evidence": {"vs_pink_db": harsh_v},
            "confidence": 0.55,
        })

    sub_v = z.get("sub", {}).get("vs_pink_db", 0.0)
    if sub_v > _SUB_VS_PINK_THRESHOLD:
        suggestions.append({
            "type": "shelf_low",
            "f_hz": 60.0,
            "q": 0.7,
            "gain_db": -float(_clip(sub_v - 2.0, 2.0, 8.0)),
            "reason": f"sub-bass {sub_v:+.1f} dB vs pink — likely rumble",
            "evidence": {"vs_pink_db": sub_v},
            "confidence": 0.5,
        })

    air_v = z.get("air", {}).get("vs_pink_db", 0.0)
    if air_v < _AIR_BELOW_PINK_THRESHOLD:
        suggestions.append({
            "type": "shelf_high",
            "f_hz": 10000.0,
            "q": 0.7,
            "gain_db": +2.0,
            "reason": f"air below pink reference by {air_v:.1f} dB",
            "evidence": {"vs_pink_db": air_v},
            "confidence": 0.45,
        })

    return suggestions


def analyze_wav(wav_path: str, options: Optional[AnalyzerOptions] = None) -> dict[str, Any]:
    options = options or AnalyzerOptions()
    x, sr = sf.read(wav_path, always_2d=False)
    x = _to_mono(np.asarray(x, dtype=np.float64))
    duration = len(x) / sr if sr else 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    rms_db = _db(rms)
    peak_db = _db(peak)
    crest = peak_db - rms_db if peak > 0 else 0.0
    silent = bool(rms_db < _SILENT_THRESHOLD_DBFS)

    report = SpectrumReport(
        sample_rate=int(sr),
        duration_s=duration,
        rms_dbfs=rms_db,
        peak_dbfs=peak_db,
        crest_factor_db=crest,
        silent=silent,
    )
    if silent:
        return report.to_dict()

    centers, rms_db_bands = _erb_band_energies(x, sr)
    f_lo, f_hi = _erb_edges(centers)
    report.erb_bands = [
        {"band": i, "f_lo_hz": float(f_lo[i]), "f_hi_hz": float(f_hi[i]),
         "f_center_hz": float(centers[i]), "rms_db": float(rms_db_bands[i]),
         "rms_db_a_weighted": float(rms_db_bands[i])}
        for i in range(len(centers))
    ]
    centers_arr = np.array([b["f_center_hz"] for b in report.erb_bands])
    if options.weighting == "a":
        offset = _a_weight_db(centers_arr)
    elif options.weighting == "iso226":
        global _iso226_warned
        if not _iso226_warned:
            _log.warning(
                "iso226 weighting is not yet implemented; falling back to "
                "no weighting. (Suppressing further warnings.)"
            )
            _iso226_warned = True
        offset = np.zeros_like(centers_arr)
    else:
        offset = np.zeros_like(centers_arr)
    for i, b in enumerate(report.erb_bands):
        b["rms_db_a_weighted"] = float(b["rms_db"] + offset[i])
    rms_db_arr = np.array([b["rms_db"] for b in report.erb_bands])
    pink_diff = _pink_diff(centers_arr, rms_db_arr, options.pink_reference_hz)
    report.pink_diff_db = [float(v) for v in pink_diff]
    c, r85, r95, fl, bw = _spectral_descriptors(x, sr, options)
    report.centroid_hz = c
    report.rolloff_85_hz = r85
    report.rolloff_95_hz = r95
    report.flatness = fl
    report.bandwidth_hz = bw
    report.resonances = _detect_resonances(x, sr, options)
    report.zones = _zones_from_bands(report.erb_bands, report.pink_diff_db)
    if options.include_suggestions and not report.silent:
        report.suggestions = _build_suggestions(report)
    # remaining sections filled in by later tasks
    return report.to_dict()


def capture_port(jack_port: str, seconds: float = 4.0,
                 output_path: Optional[str] = None) -> dict[str, Any]:
    """Capture N seconds from a JACK port to a WAV file via jack_capture.

    Args:
        jack_port: JACK port name, e.g. "Carla:audio-out1".
        seconds: capture duration; must be in (0, 60].
        output_path: optional WAV path; default is /tmp/carla-mcp-spectrum/.
    """
    if seconds <= 0 or seconds > 60:
        raise ValueError("seconds must be in (0, 60]")
    out = _validate_output_path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # jack_capture flags (verified against v0.9.73 --help2):
    #   --port <name>        : input port to record from (repeatable)
    #   --filename <path>    : output filename
    #   -d / --recording-time: stop after N seconds (plan said --duration; the
    #                          installed binary uses -d / --recording-time)
    #   --bitdepth FLOAT     : 32-bit float WAV (default; explicit for clarity)
    cmd = [
        "jack_capture",
        "--port", jack_port,
        "--filename", str(out),
        "-d", str(seconds),
        "--bitdepth", "FLOAT",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=seconds + 5)
    except FileNotFoundError as e:
        raise RuntimeError(
            "jack_capture not found — install with: sudo apt install jack-capture"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"jack_capture timed out capturing {jack_port}") from e

    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(
            f"jack_capture failed (rc={proc.returncode}): "
            f"stdout={proc.stdout[-500:]} stderr={proc.stderr[-500:]}"
        )
    info = sf.info(str(out))
    return {
        "wav_path": str(out),
        "duration_s": float(info.frames) / float(info.samplerate),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
    }


def analyze_port(jack_port: str, seconds: float = 4.0,
                 options: Optional[AnalyzerOptions] = None,
                 keep_wav: bool = False) -> dict[str, Any]:
    """Capture from a JACK port and analyze in one shot.

    Returns a SpectrumReport. WAV is deleted after analysis unless
    ``keep_wav=True``, in which case the report also contains ``wav_path``.
    """
    cap_path = _default_capture_path()
    cap = capture_port(jack_port, seconds=seconds, output_path=str(cap_path))
    try:
        report = analyze_wav(cap["wav_path"], options)
        if keep_wav:
            report["wav_path"] = cap["wav_path"]
        return report
    finally:
        if not keep_wav:
            try:
                Path(cap["wav_path"]).unlink(missing_ok=True)
            except OSError:
                pass


def register_spectrum_tools(mcp: FastMCP, bridge: CarlaBackendBridge) -> None:
    """Register spectrum-analysis MCP tools."""

    @mcp.tool()
    def capture_port_to_wav(jack_port: str, seconds: float = 4.0,
                            output_path: str | None = None) -> dict:
        """Capture audio from a JACK port to a WAV file via jack_capture.

        Args:
            jack_port: JACK port name, e.g. "Carla:audio-out1" or "loopers:loop0_out_l".
            seconds: capture duration in seconds (must be in (0, 60]).
            output_path: optional WAV output path; default is /tmp/carla-mcp-spectrum/.
        """
        return capture_port(jack_port, seconds=seconds, output_path=output_path)

    @mcp.tool()
    def analyze_wav_file(wav_path: str,
                         weighting: str = "a",
                         pink_reference_hz: float = 1000.0,
                         resonance_min_prominence_db: float = 6.0,
                         resonance_min_persistence: float = 0.5,
                         include_suggestions: bool = True) -> dict:
        """Analyze a WAV file. Returns a SpectrumReport (engineered perceptual
        features plus rule-based EQ suggestion seeds).

        Args:
            wav_path: path to a WAV file readable by soundfile.
            weighting: "none" | "a" | "iso226" (iso226 currently falls back to none).
            pink_reference_hz: anchor frequency for the pink-noise reference diff.
            resonance_min_prominence_db: detector threshold (lower = more candidates).
            resonance_min_persistence: 0..1 fraction of frames a peak must persist.
            include_suggestions: whether to compute rule-based EQ suggestion seeds.
        """
        opts = AnalyzerOptions(
            weighting=weighting,  # type: ignore[arg-type]
            pink_reference_hz=pink_reference_hz,
            resonance_min_prominence_db=resonance_min_prominence_db,
            resonance_min_persistence=resonance_min_persistence,
            include_suggestions=include_suggestions,
        )
        return analyze_wav(wav_path, opts)

    @mcp.tool()
    def analyze_port_spectrum(jack_port: str, seconds: float = 4.0,
                              weighting: str = "a",
                              pink_reference_hz: float = 1000.0,
                              resonance_min_prominence_db: float = 6.0,
                              resonance_min_persistence: float = 0.5,
                              include_suggestions: bool = True,
                              keep_wav: bool = False) -> dict:
        """Capture audio from a JACK port and analyze in one shot.

        Returns a SpectrumReport (engineered perceptual features + rule-based
        EQ suggestion seeds). The temporary WAV is deleted unless ``keep_wav=True``.
        """
        opts = AnalyzerOptions(
            weighting=weighting,  # type: ignore[arg-type]
            pink_reference_hz=pink_reference_hz,
            resonance_min_prominence_db=resonance_min_prominence_db,
            resonance_min_persistence=resonance_min_persistence,
            include_suggestions=include_suggestions,
        )
        return analyze_port(jack_port, seconds=seconds, options=opts,
                            keep_wav=keep_wav)
