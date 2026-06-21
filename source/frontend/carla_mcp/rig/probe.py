"""Test-tone playback + level measurement probe for the rig graph.

Allows the agent to validate signal flow without human ears:
play a sine into any node's input or output, then capture and
compute peak / RMS dBFS at any node's input or output.

Uses ``pw-cat`` for both playback and recording.  pw-cat on Pop_OS
24.04 / PipeWire does NOT have ``--loop`` or ``--duration`` flags, and
its ``--target`` flag does NOT honour a ``client:port`` string (it
auto-connects to the default device).  We work around all three by:
  - For playback: ``play_tone`` is a true on/off toggle.  It spawns one
    persistent ``pw-cat -p --raw -`` node (autoconnect disabled) and a
    background thread that streams a seamless sine into its stdin
    forever, so the tone holds — and its ``pw-link`` stays valid —
    until ``stop_tone`` tears the node down.  (A finite WAV would lapse
    mid-session given the gaps between agent calls.)
  - For recording: spawning pw-cat with ``-n / --sample-count`` (stop
    after ``duration * rate`` frames) and autoconnect disabled, then
    wiring the source port to the capture stream with ``pw-link``.
    pw-cat ``-r`` exits non-zero even on success, so capture is judged
    by output-file size, not return code.
"""

from __future__ import annotations

import asyncio
import math
import subprocess
import threading
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

# pw-cat --target <client:port> does NOT honour the port — it auto-connects to
# the default sink/source.  Instead we disable autoconnect and wire the stream
# explicitly with pw-link.  (Verified live on PipeWire / Pop_OS 24.04.)
AUTOCONNECT_OFF = "{ node.autoconnect=false }"


def _pwcat_props(label: str) -> str:
    """pw-cat ``-P`` properties: disable autoconnect AND set a unique
    ``node.name`` so this stream's port appears as ``<label>:output_MONO`` /
    ``<label>:input_MONO``.  That lets us match THIS pw-cat unambiguously even
    when several probe streams of the same kind are alive at once (otherwise a
    "first pw-cat: match" would cross-wire two concurrent tones)."""
    return f"{{ node.autoconnect=false node.name={label} }}"
WAV_HEADER_BYTES = 44  # a valid PCM WAV is larger than this once it has frames


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


def sine_chunk_bytes(hz: float, db: float, rate: int = SAMPLE_RATE, seconds: int = 1) -> bytes:
    """Return ``seconds`` of mono little-endian s16 sine as raw PCM bytes.

    A whole-second buffer tiles seamlessly for integer ``hz`` (a whole
    number of cycles), so it can be streamed in a loop for a continuous
    tone with no audible boundary click.
    """
    n = int(seconds * rate)
    t = np.arange(n, dtype=np.float64) / rate
    amp = _db_to_amp(db)
    pcm = np.clip(
        np.sin(2.0 * math.pi * hz * t) * amp * FULLSCALE_S16,
        -FULLSCALE_S16,
        FULLSCALE_S16 - 1,
    ).astype("<i2")
    return pcm.tobytes()


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
        pwcat_port_finder: Optional[Callable[[str], str]] = None,
        port_linker: Optional[Callable[[str, str], None]] = None,
        tone_streamer: Optional[Callable[["subprocess.Popen", float, float], Callable[[], None]]] = None,
    ) -> None:
        self._controller = controller
        self._cache_dir = Path(cache_dir) if cache_dir else Path("/tmp/carla_rig_probe")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._sp = subprocess_runner
        self._analyze = wav_analyzer
        # Injectable so tests need not parse real pw-link output.
        self._find_pwcat_port = pwcat_port_finder or self._default_find_pwcat_port
        self._link_ports = port_linker or self._default_link_ports
        # Starts the stdin sine feeder for a spawned pw-cat node; returns a
        # stop callable.  Injectable so tests need not spin a real thread.
        self._stream_tone = tone_streamer or self._default_stream_tone
        self._tone_procs: Dict[str, "subprocess.Popen"] = {}
        self._tone_stops: Dict[str, Callable[[], None]] = {}
        self._probe_seq = 0  # monotonic, for unique per-stream pw-cat node names

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

    # -- public API ------------------------------------------------------

    async def play_tone(
        self,
        node: str,
        hz: float = 440.0,
        db: float = -12.0,
        at: str = "input",
    ) -> dict:
        """Play a continuous mono sine into *node*'s input or output port.

        The tone holds until :meth:`stop_tone` (an on/off toggle).  If a
        tone is already running on this node, terminates it first.
        Returns ``{"success": True, "node", "port", "hz", "db", "linked"}``.
        """
        try:
            port = self._resolve_port(node, at)
        except ValueError as exc:
            return {"success": False, "reason": str(exc)}
        if not port:
            return {"success": False, "reason": f"no {at} ports resolved for {node!r}"}

        # Replace any in-flight tone on this node.
        if node in self._tone_procs:
            self._stop_node(node)

        # Unique node name so we can find THIS pw-cat's port even if other
        # probe tones are alive (see _pwcat_props).
        self._probe_seq += 1
        label = f"lpcprobe_play_{node}_{self._probe_seq}"

        # One persistent pw-cat node reading raw s16 from stdin; a feeder
        # thread streams the sine into it so the tone never lapses.
        cmd = [
            "pw-cat",
            "-p",
            "--raw",
            "--format",
            "s16",
            "--rate",
            str(SAMPLE_RATE),
            "--channels",
            "1",
            "-P",
            _pwcat_props(label),
            "-",
        ]
        proc = self._sp.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._tone_procs[node] = proc
        self._tone_stops[node] = self._stream_tone(proc, hz, db)

        # Wire the playback stream's output explicitly to the target input port.
        src = await self._await_pwcat_port("output", label)
        linked = bool(src)
        if src:
            self._link_ports(src, port)

        return {
            "success": True,
            "node": node,
            "port": port,
            "hz": hz,
            "db": db,
            "linked": linked,
        }

    def stop_tone(self, node: str) -> dict:
        """Terminate the tone playing on *node*, if any."""
        if node not in self._tone_procs:
            return {"success": False, "reason": "no tone playing"}
        self._stop_node(node)
        return {"success": True, "node": node}

    def stop_all_tones(self) -> dict:
        """Terminate every tracked tone process.  Returns count stopped."""
        count = 0
        for node in list(self._tone_procs.keys()):
            self._stop_node(node)
            count += 1
        return {"success": True, "stopped": count}

    def _stop_node(self, node: str) -> None:
        """Stop the feeder thread (if any) and terminate the pw-cat node."""
        stop = self._tone_stops.pop(node, None)
        if stop is not None:
            try:
                stop()
            except Exception:
                pass
        proc = self._tone_procs.pop(node, None)
        if proc is not None:
            self._terminate(proc)

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

        # Unique node name + capture file so concurrent measures don't grab
        # each other's stream port or clobber each other's WAV.
        self._probe_seq += 1
        label = f"lpcprobe_rec_{node}_{at}_{self._probe_seq}"

        n_samples = int(duration * SAMPLE_RATE)
        out_path = self._cache_dir / f"capture_{label}.wav"
        cmd = [
            "pw-cat",
            "-r",
            "--channels",
            "1",
            "--rate",
            str(SAMPLE_RATE),
            "--format",
            "s16",
            "-n",
            str(n_samples),
            "-P",
            _pwcat_props(label),
            str(out_path),
        ]
        # Spawn (not run) so we can wire the capture stream to the source port
        # after pw-cat creates it, then wait for it to capture -n samples.
        proc = self._sp.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dst = await self._await_pwcat_port("input", label)
        if dst:
            self._link_ports(port, dst)
        # Offload the blocking wait so the asyncio event loop (and all child
        # SSE traffic) keeps running during the capture window.
        try:
            await asyncio.to_thread(proc.wait, timeout=duration + 5.0)
        except Exception:
            await asyncio.to_thread(self._terminate, proc)

        # pw-cat -r exits with code 1 even on a successful finite capture, so
        # gate on the output file having real frames rather than on returncode.
        if not out_path.exists() or out_path.stat().st_size <= WAV_HEADER_BYTES:
            return {"success": False, "reason": "no output file"}

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

    async def _await_pwcat_port(
        self, kind: str, label: str, attempts: int = 30, delay: float = 0.05
    ) -> str:
        """Poll until the *label* stream port of *kind* appears, or give up.

        *kind* is ``"output"`` (playback stream) or ``"input"`` (capture stream);
        *label* is the unique ``node.name`` given to this pw-cat.  Returns the
        port string (e.g. ``<label>:output_MONO``) or ``""``.
        """
        for _ in range(attempts):
            p = self._find_pwcat_port(kind, label)
            if p:
                return p
            await asyncio.sleep(delay)
        return ""

    def _default_find_pwcat_port(self, kind: str, label: str) -> str:
        """Return the *label* stream port of *kind* via ``pw-link -o``/``-i``.

        Matches by the unique node name so concurrent probe streams don't
        resolve to each other's port.
        """
        flag = "-o" if kind == "output" else "-i"
        try:
            result = self._sp.run(["pw-link", flag], capture_output=True, text=True)
            out = result.stdout or ""
        except Exception:
            return ""
        for line in out.splitlines():
            s = line.strip()
            if s.startswith(f"{label}:") and kind in s:
                return s
        return ""

    def _default_link_ports(self, src: str, dst: str) -> None:
        """Best-effort ``pw-link src dst`` (output port → input port)."""
        try:
            self._sp.run(["pw-link", src, dst], capture_output=True, text=True)
        except Exception:
            pass

    def _default_stream_tone(self, proc, hz: float, db: float) -> Callable[[], None]:
        """Stream a seamless sine into *proc*'s stdin until stopped.

        Returns a callable that ends the stream (the write blocks at the
        real-time rate pw-cat consumes, so this also paces playback).
        """
        chunk = sine_chunk_bytes(hz, db)
        stop_evt = threading.Event()

        def feed() -> None:
            try:
                while not stop_evt.is_set():
                    proc.stdin.write(chunk)
                    proc.stdin.flush()
            except (BrokenPipeError, ValueError, OSError):
                pass

        threading.Thread(target=feed, daemon=True).start()

        def stop() -> None:
            stop_evt.set()
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass

        return stop

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
