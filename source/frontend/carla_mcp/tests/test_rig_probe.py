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


def _make_probe(tmp_path: Path, controller=None, sp=None, analyzer=None) -> RigProbe:
    controller = controller or _make_controller_with_node()
    sp = sp or MagicMock(Popen=MagicMock(), run=MagicMock())
    return RigProbe(
        controller,
        cache_dir=tmp_path,
        subprocess_runner=sp,
        wav_analyzer=analyzer or analyze_wav,
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
        probe = _make_probe(tmp_path, controller=controller, sp=sp)

        result = await probe.play_tone("strat", hz=440.0, db=-12.0, at="input")

        assert result == {
            "success": True,
            "node": "strat",
            "port": "CarlaChain_strat:audio-in1",
            "hz": 440.0,
            "db": -12.0,
        }
        controller._sink_ports.assert_called_once()
        sp.Popen.assert_called_once()
        cmd = sp.Popen.call_args.args[0]
        assert cmd[0] == "pw-cat"
        assert "-p" in cmd
        assert "--target" in cmd
        assert "CarlaChain_strat:audio-in1" in cmd

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


# ---------------------------------------------------------------------------
# RigProbe.measure_level
# ---------------------------------------------------------------------------


class TestMeasureLevel:
    @pytest.mark.asyncio
    async def test_invokes_pw_cat_record_and_returns_db(self, tmp_path):
        controller = _make_controller_with_node("strat")
        sp = MagicMock()

        # When pw-cat "runs," write a constant-amp WAV at -6 dB to the
        # expected capture path so the analyzer reads it.
        def fake_run(cmd, **kwargs):
            out_path = Path(cmd[-1])
            _write_constant_amp_wav(out_path, db=-6.0, duration_s=0.5)
            return MagicMock(returncode=0)

        sp.run.side_effect = fake_run
        probe = _make_probe(tmp_path, controller=controller, sp=sp)

        result = await probe.measure_level("strat", at="output", duration=0.5)

        assert result["success"] is True
        assert result["node"] == "strat"
        assert result["port"] == "CarlaChain_strat:audio-out1"
        assert result["duration_s"] == 0.5
        assert abs(result["peak_db"] - (-6.0)) < 0.5
        assert abs(result["rms_db"] - (-6.0)) < 0.5
        cmd = sp.run.call_args.args[0]
        assert cmd[0] == "pw-cat"
        assert "-r" in cmd
        # -n sample-count == duration * rate
        assert "-n" in cmd
        n_idx = cmd.index("-n")
        assert cmd[n_idx + 1] == str(int(0.5 * SAMPLE_RATE))

    @pytest.mark.asyncio
    async def test_silent_capture_reports_floor(self, tmp_path):
        controller = _make_controller_with_node("strat")
        sp = MagicMock()

        def fake_run(cmd, **kwargs):
            out_path = Path(cmd[-1])
            with wave.open(str(out_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(np.zeros(int(0.5 * SAMPLE_RATE), dtype=np.int16).tobytes())
            return MagicMock(returncode=0)

        sp.run.side_effect = fake_run
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
        sp.run.return_value = MagicMock(returncode=1)  # no file written
        probe = _make_probe(tmp_path, controller=controller, sp=sp)

        result = await probe.measure_level("strat", at="output", duration=0.1)
        assert result["success"] is False
        assert "no output file" in result["reason"]
