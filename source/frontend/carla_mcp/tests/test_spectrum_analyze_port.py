from pathlib import Path
import numpy as np
import soundfile as sf
from unittest.mock import patch
from carla_mcp.tools.spectrum import analyze_port


def _stub_capture(jack_port, seconds, output_path):
    sr = 48000
    t = np.arange(int(seconds * sr)) / sr
    sf.write(output_path, (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32),
             sr, subtype="FLOAT")
    return {"wav_path": output_path, "duration_s": seconds,
            "sample_rate": sr, "channels": 1}


def test_analyze_port_returns_report_and_deletes_wav(tmp_path):
    captured_paths = []

    def _capture(jack_port, seconds=4.0, output_path=None):
        path = output_path or str(tmp_path / "auto.wav")
        captured_paths.append(path)
        return _stub_capture(jack_port, seconds, path)

    with patch("carla_mcp.tools.spectrum.capture_port", side_effect=_capture):
        report = analyze_port("Carla:audio-out1", seconds=0.5)

    assert "erb_bands" in report and len(report["erb_bands"]) > 0
    assert report["silent"] is False
    assert not Path(captured_paths[0]).exists(), \
        f"WAV should have been deleted, but {captured_paths[0]} still exists"


def test_analyze_port_keeps_wav_when_requested(tmp_path):
    out = tmp_path / "kept.wav"

    def _capture(jack_port, seconds=4.0, output_path=None):
        path = output_path or str(out)
        return _stub_capture(jack_port, seconds, path)

    with patch("carla_mcp.tools.spectrum.capture_port", side_effect=_capture):
        report = analyze_port("Carla:audio-out1", seconds=0.5, keep_wav=True)

    assert "wav_path" in report
    assert Path(report["wav_path"]).exists()
