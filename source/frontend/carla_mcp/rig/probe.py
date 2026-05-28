"""Test-tone playback + level measurement probe for the rig graph.

Allows the agent to validate signal flow without human ears:
play a sine into any node's input or output, then capture and
compute peak / RMS dBFS at any node's input or output.

Uses ``pw-cat`` for both playback and recording.  pw-cat on Pop_OS
24.04 / PipeWire does NOT have ``--loop`` or ``--duration`` flags.
We work around this by:
  - For playback: generating a longer WAV (default 10 s) so the
    tone runs for a while; if it needs to run indefinitely, the
    process is just spawned and held — caller invokes ``stop_tone``.
  - For recording: using ``-n / --sample-count`` to stop after a
    fixed number of frames (``duration * rate``).
"""

from __future__ import annotations

import asyncio
import math
import subprocess
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Optional

import numpy as np

if TYPE_CHECKING:
    from carla_mcp.rig.controller import RigController


SAMPLE_RATE = 48000
TONE_DURATION_S = 10.0  # length of the cached sine WAV
DB_FLOOR = -120.0
FULLSCALE_S16 = 32768.0


def _db_to_amp(db: float) -> float:
    """Convert dBFS to linear amplitude in [0, 1]."""
    return 10.0 ** (db / 20.0)


def _amp_to_db(amp: float) -> float:
    """Convert linear amplitude to dBFS, clamped to ``DB_FLOOR``."""
    if amp <= 0.0:
        return DB_FLOOR
    db = 20.0 * math.log10(amp)
    return max(db, DB_FLOOR)


def generate_sine_wav(
    path: Path,
    hz: float,
    db: float,
    duration_s: float = TONE_DURATION_S,
    rate: int = SAMPLE_RATE,
) -> Path:
    """Write a mono 16-bit PCM sine WAV to *path*.

    Peak amplitude corresponds to ``db`` dBFS (relative to s16 fullscale).
    Returns the path written.
    """
    n_samples = int(duration_s * rate)
    t = np.arange(n_samples, dtype=np.float64) / rate
    amp = _db_to_amp(db)
    samples = np.sin(2.0 * math.pi * hz * t) * amp
    pcm = np.clip(samples * FULLSCALE_S16, -FULLSCALE_S16, FULLSCALE_S16 - 1).astype(np.int16)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    return path


def analyze_wav(path: Path) -> Dict[str, float]:
    """Read a 16-bit PCM mono WAV and return peak + RMS dBFS."""
    with wave.open(str(path), "rb") as wf:
        n_frames = wf.getnframes()
        sample_width = wf.getsampwidth()
        raw = wf.readframes(n_frames)

    if sample_width != 2:
        raise ValueError(f"only 16-bit PCM supported, got {sample_width * 8}-bit")

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    if samples.size == 0:
        return {"peak_db": DB_FLOOR, "rms_db": DB_FLOOR}

    peak_amp = float(np.max(np.abs(samples)) / FULLSCALE_S16)
    rms_amp = float(np.sqrt(np.mean(samples * samples)) / FULLSCALE_S16)
    return {"peak_db": _amp_to_db(peak_amp), "rms_db": _amp_to_db(rms_amp)}


class RigProbe:
    """Owns cached sine WAVs and active pw-cat playback processes.

    Parameters
    ----------
    controller:
        The :class:`RigController` whose ``_graph`` and port resolvers
        are used to map node names to JACK port strings.
    cache_dir:
        Directory for cached sine WAVs.  Defaults to ``/tmp/carla_rig_probe``.
    subprocess_runner:
        Object exposing ``Popen`` + ``run`` (defaults to stdlib ``subprocess``).
        Injectable for tests.
    wav_analyzer:
        Callable ``Path -> dict`` returning ``{"peak_db", "rms_db"}``.
        Defaults to :func:`analyze_wav`.
    """

    def __init__(
        self,
        controller: "RigController",
        cache_dir: Optional[Path] = None,
        subprocess_runner=subprocess,
        wav_analyzer: Callable[[Path], Dict[str, float]] = analyze_wav,
    ) -> None:
        self._controller = controller
        self._cache_dir = Path(cache_dir) if cache_dir else Path("/tmp/carla_rig_probe")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._sp = subprocess_runner
        self._analyze = wav_analyzer
        self._tone_procs: Dict[str, "subprocess.Popen"] = {}

    # -- port resolution -------------------------------------------------

    def _resolve_port(self, node_name: str, at: str) -> str:
        """Resolve the first JACK port for *node_name* at ``"input"`` or ``"output"``.

        Raises ``ValueError`` for invalid ``at`` or missing node, and
        returns ``""`` if no ports could be resolved.
        """
        if at not in ("input", "output"):
            raise ValueError(f"at must be 'input' or 'output', got {at!r}")
        if not self._controller._graph.has_node(node_name):
            raise ValueError(f"node {node_name!r} not in rig graph")
        node = self._controller._graph.get_node(node_name)
        ports = (
            self._controller._sink_ports(node)
            if at == "input"
            else self._controller._source_ports(node)
        )
        return ports[0] if ports else ""

    # -- tone cache ------------------------------------------------------

    def _tone_path(self, hz: float, db: float) -> Path:
        return self._cache_dir / f"sine_{hz:g}hz_{db:g}db.wav"

    def _ensure_tone(self, hz: float, db: float) -> Path:
        path = self._tone_path(hz, db)
        if not path.exists():
            generate_sine_wav(path, hz, db)
        return path

    # -- public API ------------------------------------------------------

    async def play_tone(
        self,
        node: str,
        hz: float = 440.0,
        db: float = -12.0,
        at: str = "input",
    ) -> dict:
        """Play a mono sine into *node*'s input or output port.

        If a tone is already running on this node, terminates it first.
        Returns ``{"success": True, "node", "port", "hz", "db"}``.
        """
        try:
            port = self._resolve_port(node, at)
        except ValueError as exc:
            return {"success": False, "reason": str(exc)}
        if not port:
            return {"success": False, "reason": f"no {at} ports resolved for {node!r}"}

        wav = self._ensure_tone(hz, db)

        # Replace any in-flight tone on this node.
        if node in self._tone_procs:
            self._terminate(self._tone_procs.pop(node))

        cmd = [
            "pw-cat",
            "-p",
            "--target",
            port,
            "--channels",
            "1",
            "--rate",
            str(SAMPLE_RATE),
            str(wav),
        ]
        proc = self._sp.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._tone_procs[node] = proc

        # Tiny yield so the spawned proc gets a chance to connect.
        await asyncio.sleep(0)

        return {"success": True, "node": node, "port": port, "hz": hz, "db": db}

    def stop_tone(self, node: str) -> dict:
        """Terminate the tone playing on *node*, if any."""
        proc = self._tone_procs.pop(node, None)
        if proc is None:
            return {"success": False, "reason": "no tone playing"}
        self._terminate(proc)
        return {"success": True, "node": node}

    def stop_all_tones(self) -> dict:
        """Terminate every tracked tone process.  Returns count stopped."""
        count = 0
        for node, proc in list(self._tone_procs.items()):
            self._terminate(proc)
            del self._tone_procs[node]
            count += 1
        return {"success": True, "stopped": count}

    async def measure_level(
        self,
        node: str,
        at: str = "output",
        duration: float = 0.5,
    ) -> dict:
        """Record from *node* for *duration* seconds and return peak/RMS dBFS."""
        try:
            port = self._resolve_port(node, at)
        except ValueError as exc:
            return {"success": False, "reason": str(exc)}
        if not port:
            return {"success": False, "reason": f"no {at} ports resolved for {node!r}"}

        n_samples = int(duration * SAMPLE_RATE)
        out_path = self._cache_dir / f"capture_{node}_{at}.wav"
        cmd = [
            "pw-cat",
            "-r",
            "--target",
            port,
            "--channels",
            "1",
            "--rate",
            str(SAMPLE_RATE),
            "--format",
            "s16",
            "-n",
            str(n_samples),
            str(out_path),
        ]
        # Run sync — pw-cat exits once -n samples are captured.
        try:
            self._sp.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=duration + 5.0,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "reason": "pw-cat capture timed out"}

        if not out_path.exists():
            return {"success": False, "reason": "pw-cat produced no output file"}

        levels = self._analyze(out_path)
        return {
            "success": True,
            "node": node,
            "port": port,
            "duration_s": duration,
            "peak_db": levels["peak_db"],
            "rms_db": levels["rms_db"],
        }

    # -- helpers ---------------------------------------------------------

    def _terminate(self, proc) -> None:
        """Best-effort terminate + wait on a Popen."""
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:
                pass
