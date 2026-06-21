"""Tests for rig/probe.py — RigProbe test-tone + level-measurement.

Subprocess (pw-cat) is mocked.  WAV generation + dB analysis are
exercised with real numpy + stdlib wave in pytest tmp_path.
"""

from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from carla_mcp.rig.graph import Node, RigGraph
from carla_mcp.rig.probe import (
    DB_FLOOR,
    FULLSCALE_S16,
    SAMPLE_RATE,
    RigProbe,
    analyze_wav,
    generate_sine_wav,
    sine_chunk_bytes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_controller_with_node(name: str = "strat"):
    """Return a fake controller exposing _graph, _source_ports, _sink_ports."""
    graph = RigGraph()
    graph.add_node(Node(name=name, kind="track", jack_client=f"CarlaChain_{name}"))
    controller = MagicMock()
    controller._graph = graph
    controller._source_ports = MagicMock(
        return_value=[f"CarlaChain_{name}:audio-out1", f"CarlaChain_{name}:audio-out2"]
    )
    controller._sink_ports = MagicMock(
        return_value=[f"CarlaChain_{name}:audio-in1", f"CarlaChain_{name}:audio-in2"]
    )
    return controller


def _make_probe(tmp_path: Path, controller=None, sp=None, analyzer=None,
                port_finder=None, linker=None, streamer=None) -> RigProbe:
    controller = controller or _make_controller_with_node()
    sp = sp or MagicMock(Popen=MagicMock(), run=MagicMock())
    # By default, resolve pw-cat stream ports instantly without touching
    # real pw-link, and record link calls on the provided/created mock.
    if port_finder is None:
        port_finder = lambda kind, label: f"pw-cat:{kind}_MONO"
    if linker is None:
        linker = MagicMock()
    # No-op streamer by default so play_tone doesn't spin a real feeder
    # thread; returns a stop callable (also a mock).
    if streamer is None:
        streamer = MagicMock(return_value=MagicMock())
    return RigProbe(
        controller,
        cache_dir=tmp_path,
        subprocess_runner=sp,
        wav_analyzer=analyzer or analyze_wav,
        pwcat_port_finder=port_finder,
        port_linker=linker,
        tone_streamer=streamer,
    )


def _write_constant_amp_wav(path: Path, db: float, duration_s: float = 0.5):
    """Write a mono 16-bit PCM WAV at constant amplitude corresponding to *db* dBFS."""
    n = int(duration_s * SAMPLE_RATE)
    amp = 10.0 ** (db / 20.0)
    samples = np.full(n, amp, dtype=np.float64)
    pcm = np.clip(samples * FULLSCALE_S16, -FULLSCALE_S16, FULLSCALE_S16 - 1).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# WAV generation + analysis (real numpy / wave, no mocks)
# ---------------------------------------------------------------------------


class TestSineGeneration:
    def test_generates_wav_with_correct_rate_and_length(self, tmp_path):
        out = generate_sine_wav(tmp_path / "sine.wav", hz=440.0, db=-12.0, duration_s=1.0)
        with wave.open(str(out), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == SAMPLE_RATE
            assert wf.getnframes() == SAMPLE_RATE  # 1 second

    def test_peak_amplitude_matches_requested_db(self, tmp_path):
        out = generate_sine_wav(tmp_path / "sine.wav", hz=440.0, db=-12.0, duration_s=0.5)
        levels = analyze_wav(out)
        # Sine peak should be within 0.5 dB of requested
        assert abs(levels["peak_db"] - (-12.0)) < 0.5


class TestAnalyzeWav:
    def test_known_amplitude_returns_expected_db(self, tmp_path):
        wav = tmp_path / "const.wav"
        _write_constant_amp_wav(wav, db=-6.0, duration_s=0.5)
        levels = analyze_wav(wav)
        # Constant amp → peak ≈ rms ≈ -6 dB
        assert abs(levels["peak_db"] - (-6.0)) < 0.5
        assert abs(levels["rms_db"] - (-6.0)) < 0.5

    def test_silent_input_floors_at_minus_120(self, tmp_path):
        wav = tmp_path / "silent.wav"
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(np.zeros(SAMPLE_RATE // 2, dtype=np.int16).tobytes())
        levels = analyze_wav(wav)
        assert levels["peak_db"] == DB_FLOOR
        assert levels["rms_db"] == DB_FLOOR


# ---------------------------------------------------------------------------
# RigProbe.play_tone
# ---------------------------------------------------------------------------


class TestPlayTone:
    @pytest.mark.asyncio
    async def test_resolves_input_port_and_spawns_pw_cat(self, tmp_path):
        controller = _make_controller_with_node("strat")
        sp = MagicMock()
        linker = MagicMock()
        probe = _make_probe(tmp_path, controller=controller, sp=sp, linker=linker)

        result = await probe.play_tone("strat", hz=440.0, db=-12.0, at="input")

        assert result == {
            "success": True,
            "node": "strat",
            "port": "CarlaChain_strat:audio-in1",
            "hz": 440.0,
            "db": -12.0,
            "linked": True,
        }
        controller._sink_ports.assert_called_once()
        sp.Popen.assert_called_once()
        cmd = sp.Popen.call_args.args[0]
        assert cmd[0] == "pw-cat"
        assert "-p" in cmd
        # continuous tone: raw s16 streamed from stdin (last arg "-")
        assert "--raw" in cmd
        assert cmd[-1] == "-"
        assert sp.Popen.call_args.kwargs["stdin"] is subprocess.PIPE
        # autoconnect disabled, no --target (which pw-cat ignores for ports)
        assert "--target" not in cmd
        assert "-P" in cmd
        # autoconnect disabled + a unique node.name for unambiguous matching
        props = cmd[cmd.index("-P") + 1]
        assert "node.autoconnect=false" in props
        assert "node.name=" in props
        # playback stream output wired explicitly to the target input port
        linker.assert_called_once_with("pw-cat:output_MONO", "CarlaChain_strat:audio-in1")

    @pytest.mark.asyncio
    async def test_uses_source_ports_when_at_is_output(self, tmp_path):
        controller = _make_controller_with_node("strat")
        sp = MagicMock()
        probe = _make_probe(tmp_path, controller=controller, sp=sp)

        result = await probe.play_tone("strat", at="output")
        assert result["success"] is True
        assert result["port"] == "CarlaChain_strat:audio-out1"
        controller._source_ports.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_at_returns_error(self, tmp_path):
        probe = _make_probe(tmp_path)
        result = await probe.play_tone("strat", at="sideways")
        assert result["success"] is False
        assert "input" in result["reason"] or "output" in result["reason"]

    @pytest.mark.asyncio
    async def test_unknown_node_returns_error(self, tmp_path):
        probe = _make_probe(tmp_path)
        result = await probe.play_tone("ghost", at="input")
        assert result["success"] is False
        assert "not in rig graph" in result["reason"]

    @pytest.mark.asyncio
    async def test_second_play_terminates_first_proc(self, tmp_path):
        sp = MagicMock()
        proc1 = MagicMock()
        proc2 = MagicMock()
        sp.Popen.side_effect = [proc1, proc2]
        probe = _make_probe(tmp_path, sp=sp)

        await probe.play_tone("strat", at="input")
        await probe.play_tone("strat", at="input")

        proc1.terminate.assert_called_once()
        assert probe._tone_procs["strat"] is proc2

    @pytest.mark.asyncio
    async def test_no_ports_resolved_returns_error(self, tmp_path):
        controller = _make_controller_with_node()
        controller._sink_ports.return_value = []
        probe = _make_probe(tmp_path, controller=controller)
        result = await probe.play_tone("strat", at="input")
        assert result["success"] is False
        assert "no input ports" in result["reason"]

    def test_find_pwcat_port_matches_by_label_not_first(self, tmp_path):
        # With two probe pw-cat streams of the same kind alive, the finder must
        # return THIS stream's port (by node name), not the first one.
        sp = MagicMock()
        sp.run.return_value = MagicMock(
            stdout=(
                "lpcprobe_play_a_1:output_MONO\n"
                "lpcprobe_play_b_2:output_MONO\n"
            )
        )
        probe = _make_probe(tmp_path, sp=sp)
        # call the real finder directly (the injected one is bypassed here)
        got = probe._default_find_pwcat_port("output", "lpcprobe_play_b_2")
        assert got == "lpcprobe_play_b_2:output_MONO"


# ---------------------------------------------------------------------------
# RigProbe.stop_tone / stop_all_tones
# ---------------------------------------------------------------------------


class TestStopTone:
    def test_stop_tone_terminates_and_removes(self, tmp_path):
        sp = MagicMock()
        probe = _make_probe(tmp_path, sp=sp)
        proc = MagicMock()
        probe._tone_procs["strat"] = proc

        result = probe.stop_tone("strat")

        assert result["success"] is True
        proc.terminate.assert_called_once()
        assert "strat" not in probe._tone_procs

    def test_stop_tone_no_tone_returns_false(self, tmp_path):
        probe = _make_probe(tmp_path)
        result = probe.stop_tone("nothing")
        assert result["success"] is False
        assert result["reason"] == "no tone playing"

    def test_stop_all_tones_stops_each(self, tmp_path):
        probe = _make_probe(tmp_path)
        p1, p2 = MagicMock(), MagicMock()
        probe._tone_procs["a"] = p1
        probe._tone_procs["b"] = p2

        result = probe.stop_all_tones()

        assert result["stopped"] == 2
        p1.terminate.assert_called_once()
        p2.terminate.assert_called_once()
        assert probe._tone_procs == {}


class TestContinuousToggle:
    """play_tone is an on/off toggle backed by a streaming feeder."""

    def test_sine_chunk_bytes_length_and_amplitude(self):
        raw = sine_chunk_bytes(440.0, -6.0, rate=SAMPLE_RATE, seconds=1)
        samples = np.frombuffer(raw, dtype="<i2")
        assert samples.size == SAMPLE_RATE  # one whole second
        peak = float(np.max(np.abs(samples))) / FULLSCALE_S16
        assert abs(20.0 * math.log10(peak) - (-6.0)) < 0.5

    @pytest.mark.asyncio
    async def test_play_starts_streamer_and_stop_invokes_it(self, tmp_path):
        sp = MagicMock()
        proc = MagicMock()
        sp.Popen.return_value = proc
        stop_cb = MagicMock()
        streamer = MagicMock(return_value=stop_cb)
        probe = _make_probe(tmp_path, sp=sp, streamer=streamer)

        await probe.play_tone("strat", hz=440.0, db=-12.0, at="input")
        streamer.assert_called_once_with(proc, 440.0, -12.0)

        probe.stop_tone("strat")
        stop_cb.assert_called_once()
        assert "strat" not in probe._tone_stops

    @pytest.mark.asyncio
    async def test_second_play_stops_first_streamer(self, tmp_path):
        sp = MagicMock()
        sp.Popen.side_effect = [MagicMock(), MagicMock()]
        stop1, stop2 = MagicMock(), MagicMock()
        streamer = MagicMock(side_effect=[stop1, stop2])
        probe = _make_probe(tmp_path, sp=sp, streamer=streamer)

        await probe.play_tone("strat", at="input")
        await probe.play_tone("strat", at="input")

        stop1.assert_called_once()


# ---------------------------------------------------------------------------
# RigProbe.measure_level
# ---------------------------------------------------------------------------


class TestMeasureLevel:
    @pytest.mark.asyncio
    async def test_invokes_pw_cat_record_and_returns_db(self, tmp_path):
        controller = _make_controller_with_node("strat")
        sp = MagicMock()
        linker = MagicMock()

        # When pw-cat is spawned, write a constant-amp WAV at -6 dB to the
        # expected capture path so the analyzer reads it; return a proc whose
        # wait() mimics pw-cat -r exiting non-zero even on success.
        def fake_popen(cmd, **kwargs):
            out_path = Path(cmd[-1])
            _write_constant_amp_wav(out_path, db=-6.0, duration_s=0.5)
            proc = MagicMock()
            proc.wait.return_value = 1
            return proc

        sp.Popen.side_effect = fake_popen
        probe = _make_probe(tmp_path, controller=controller, sp=sp, linker=linker)

        result = await probe.measure_level("strat", at="output", duration=0.5)

        assert result["success"] is True
        assert result["node"] == "strat"
        assert result["port"] == "CarlaChain_strat:audio-out1"
        assert result["duration_s"] == 0.5
        assert abs(result["peak_db"] - (-6.0)) < 0.5
        assert abs(result["rms_db"] - (-6.0)) < 0.5
        cmd = sp.Popen.call_args.args[0]
        assert cmd[0] == "pw-cat"
        assert "-r" in cmd
        assert "--target" not in cmd
        assert "-P" in cmd
        # -n sample-count == duration * rate
        assert "-n" in cmd
        n_idx = cmd.index("-n")
        assert cmd[n_idx + 1] == str(int(0.5 * SAMPLE_RATE))
        # capture stream wired from the source port (out) → pw-cat input
        linker.assert_called_once_with("CarlaChain_strat:audio-out1", "pw-cat:input_MONO")

    @pytest.mark.asyncio
    async def test_measure_level_does_not_block_event_loop(self, tmp_path):
        # A slow (blocking) proc.wait must run off-loop so other coroutines
        # keep progressing.  If it blocked the loop, the ticker below could
        # not advance while the capture "runs".
        import asyncio
        import time as _time

        controller = _make_controller_with_node("strat")
        sp = MagicMock()

        def fake_popen(cmd, **kwargs):
            out_path = Path(cmd[-1])
            _write_constant_amp_wav(out_path, db=-6.0, duration_s=0.1)
            proc = MagicMock()
            proc.wait.side_effect = lambda timeout=None: _time.sleep(0.2)
            return proc

        sp.Popen.side_effect = fake_popen
        probe = _make_probe(tmp_path, controller=controller, sp=sp)

        progressed = []

        async def ticker():
            for _ in range(20):
                progressed.append(1)
                await asyncio.sleep(0.01)

        measure = asyncio.create_task(probe.measure_level("strat", at="output", duration=0.1))
        tick = asyncio.create_task(ticker())
        await measure
        progress_during_measure = len(progressed)
        await tick

        assert progress_during_measure >= 3  # loop kept running during the wait

    @pytest.mark.asyncio
    async def test_silent_capture_reports_floor(self, tmp_path):
        controller = _make_controller_with_node("strat")
        sp = MagicMock()

        def fake_popen(cmd, **kwargs):
            out_path = Path(cmd[-1])
            with wave.open(str(out_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(np.zeros(int(0.5 * SAMPLE_RATE), dtype=np.int16).tobytes())
            proc = MagicMock()
            proc.wait.return_value = 1
            return proc

        sp.Popen.side_effect = fake_popen
        probe = _make_probe(tmp_path, controller=controller, sp=sp)

        result = await probe.measure_level("strat", at="output", duration=0.5)
        assert result["peak_db"] == DB_FLOOR
        assert result["rms_db"] == DB_FLOOR

    @pytest.mark.asyncio
    async def test_invalid_at_returns_error(self, tmp_path):
        probe = _make_probe(tmp_path)
        result = await probe.measure_level("strat", at="bogus")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_pw_cat_failure_to_produce_file_returns_error(self, tmp_path):
        controller = _make_controller_with_node("strat")
        sp = MagicMock()
        # Popen spawns but no file is ever written (capture failed).
        sp.Popen.return_value = MagicMock(wait=MagicMock(return_value=1))
        probe = _make_probe(tmp_path, controller=controller, sp=sp)

        result = await probe.measure_level("strat", at="output", duration=0.1)
        assert result["success"] is False
        assert "no output file" in result["reason"]
