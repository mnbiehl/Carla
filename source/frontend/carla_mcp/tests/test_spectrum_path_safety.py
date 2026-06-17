from pathlib import Path
import pytest
from carla_mcp.tools.spectrum import capture_port, _DEFAULT_TMP_ROOT


def test_output_path_outside_tmp_rejected(tmp_path):
    with pytest.raises(ValueError, match="must be under"):
        capture_port("system:capture_1", seconds=0.5,
                     output_path=str(tmp_path / "evil.wav"))


def test_output_path_traversal_rejected():
    with pytest.raises(ValueError, match="must be under"):
        capture_port(
            "system:capture_1", seconds=0.5,
            output_path=str(_DEFAULT_TMP_ROOT / ".." / ".." / "etc" / "passwd"),
        )


def test_output_path_symlink_rejected(tmp_path):
    _DEFAULT_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "real.wav"
    target.write_bytes(b"")
    link = _DEFAULT_TMP_ROOT / "linky.wav"
    if link.exists():
        link.unlink()
    link.symlink_to(target)
    try:
        with pytest.raises(ValueError, match="symlink"):
            capture_port("system:capture_1", seconds=0.5,
                         output_path=str(link))
    finally:
        link.unlink(missing_ok=True)


def test_output_path_under_tmp_accepted(tmp_path, monkeypatch):
    """Inside _DEFAULT_TMP_ROOT, the path validator returns the resolved path
    without raising. (Capture itself is mocked elsewhere; this test only
    exercises the validator path through capture_port up to subprocess.)"""
    from unittest.mock import patch, MagicMock
    import subprocess
    safe = _DEFAULT_TMP_ROOT / "ok.wav"
    safe.parent.mkdir(parents=True, exist_ok=True)
    if safe.exists():
        safe.unlink()
    fake = MagicMock(return_value=subprocess.CompletedProcess(
        ["jack_capture"], 0, "", ""))
    # We need the WAV to exist after jack_capture "runs" so sf.info works.
    def _side(cmd, *a, **kw):
        # Find the filename arg and write a tiny valid WAV.
        import numpy as np, soundfile as sf
        for i, tok in enumerate(cmd):
            if tok == "--filename":
                sr = 48000
                t = np.arange(int(0.1 * sr)) / sr
                sf.write(cmd[i + 1],
                         (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32),
                         sr, subtype="FLOAT")
                break
        return subprocess.CompletedProcess(cmd, 0, "", "")
    fake.side_effect = _side
    with patch("carla_mcp.tools.spectrum.subprocess.run", fake):
        meta = capture_port("system:capture_1", seconds=0.1,
                            output_path=str(safe))
    assert meta["wav_path"] == str(safe)
    safe.unlink(missing_ok=True)
