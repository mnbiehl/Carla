import subprocess
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from unittest.mock import patch, MagicMock
from carla_mcp.tools.spectrum import capture_port, _DEFAULT_TMP_ROOT


def _fake_jack_capture(out_path, sr=48000, seconds=0.2):
    """Write a tiny WAV at out_path the way jack_capture would."""
    t = np.arange(int(seconds * sr)) / sr
    sf.write(out_path, (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32),
             sr, subtype="FLOAT")


def test_capture_port_invokes_jack_capture(tmp_path):
    out = _DEFAULT_TMP_ROOT / "cap.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    fake_run = MagicMock()
    def _side_effect(cmd, *a, **kw):
        # Find filename arg in cmd and write a fake WAV there
        # (the implementer can use whichever flag jack_capture actually expects)
        for i, tok in enumerate(cmd):
            if tok in ("--filename", "-fn", "-o"):
                _fake_jack_capture(cmd[i + 1])
                break
        else:
            # Fallback: last positional arg is the output path
            _fake_jack_capture(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, "", "")
    fake_run.side_effect = _side_effect

    with patch("carla_mcp.tools.spectrum.subprocess.run", fake_run):
        meta = capture_port("system:capture_1", seconds=0.2,
                            output_path=str(out))

    assert meta["wav_path"] == str(out)
    assert meta["sample_rate"] == 48000
    assert 0.1 < meta["duration_s"] < 0.5
    assert meta["channels"] in (1, 2)


def test_capture_port_missing_binary(tmp_path):
    out = _DEFAULT_TMP_ROOT / "missing_bin.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    with patch("carla_mcp.tools.spectrum.subprocess.run",
               side_effect=FileNotFoundError("jack_capture")):
        with pytest.raises(RuntimeError, match="jack_capture"):
            capture_port("system:capture_1", seconds=0.2,
                         output_path=str(out))


def test_capture_port_invalid_duration(tmp_path):
    # Invalid duration short-circuits before path validation, so an arbitrary
    # path is fine here.
    with pytest.raises(ValueError):
        capture_port("system:capture_1", seconds=0,
                     output_path=str(tmp_path / "x.wav"))
    with pytest.raises(ValueError):
        capture_port("system:capture_1", seconds=120,
                     output_path=str(tmp_path / "x.wav"))
