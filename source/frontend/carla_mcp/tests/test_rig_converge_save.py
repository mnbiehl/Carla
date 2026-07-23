"""Tests for rig/converge.do_save — v3 emit + self-verification + link lifting."""

import asyncio
import json
from pathlib import Path

from carla_mcp.rig.converge import RigOps, do_save
from carla_mcp.rig.observe import Link, ObservedState
from carla_mcp.rig.session import read_session

MON0 = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"
CAPTURE = "alsa_input.usb-F-00.pro-input-0:capture_AUX0"
PACER = "a2j:Pacer [32] (capture): Pacer MIDI 1"
MIDI_IN = "loopers:loopers_midi_in"


class SaveFakeOps(RigOps):
    def __init__(self):
        self.outputs = ["loopers:loop0_out_l", "loopers:loop0_out_r",
                        "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2",
                        CAPTURE, PACER]
        self.inputs = ["loopers:loop0_in_l", "loopers:loop0_in_r",
                       "CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
                       MIDI_IN, MON0]
        self.links = [
            Link("loopers:loop0_out_l", "CarlaChain_strat:audio-in1"),
            Link("loopers:loop0_out_r", "CarlaChain_strat:audio-in2"),
            Link(CAPTURE, "loopers:loop0_in_l"),
            Link(CAPTURE, "loopers:loop0_in_r"),
            Link(PACER, MIDI_IN),
        ]

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph else []
        return ObservedState(links=self.links, output_ports=self.outputs,
                             input_ports=self.inputs,
                             unit_status={u.name: True for u in units})

    async def export_rig_state(self, chains_dir):
        Path(chains_dir).mkdir(parents=True, exist_ok=True)
        chain = Path(chains_dir) / "strat.carxp"
        chain.write_text("<carla/>")
        return {
            "version": 1,
            "nodes": [
                {"name": "loopers:loop0_out", "kind": "endpoint", "instance": None,
                 "jack_client": "loopers:loop0_out", "source": None, "effects": []},
                {"name": "strat", "kind": "track", "instance": "strat",
                 "jack_client": "CarlaChain_strat", "source": "loopers:loop0_out",
                 "effects": [{"role": "eq", "handle": "strat/eq",
                              "plugin": "x42-eq", "bypassed": False}],
                 "chain_file": str(chain)},
            ],
            "edges": [{"src": "loopers:loop0_out", "dst": "strat", "gain_db": 0.0}],
            "errors": [],
        }

    async def save_carla_project(self, path):
        Path(path).write_text("<carla/>")
        return None

    async def looper_get_state(self):
        return {"main_muted": True, "all_muted": False,
                "loopers": [{"id": 7, "port_index": 0, "mode": "Playing",
                             "level_db": 0.0, "pan": 0.0, "input_source": None}]}

    async def looper_save_session_at(self, dir_path):
        d = Path(dir_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.loopers").write_text(json.dumps({"loopers": []}))
        return None


class TestDoSave:
    def test_save_emits_verified_v3(self, tmp_path):
        sdir = tmp_path / "s"
        report = asyncio.run(do_save("s", sdir, SaveFakeOps()))
        assert report.splitlines()[0] == "OK", report
        sess = read_session(sdir)
        assert sess.carla_project == "carla_project.carxp"
        assert sess.looper_session_dir == "looper"
        assert sess.graph.get_node("loop:0").looper_id == 7
        assert sess.graph.get_node("app:looper").main_muted is True
        assert sess.graph.get_node("strat").chain_file == "chains/strat.carxp"

    def test_loop_edge_normalized_not_duplicated(self, tmp_path):
        sdir = tmp_path / "s"
        asyncio.run(do_save("s", sdir, SaveFakeOps()))
        sess = read_session(sdir)
        loop_edges = [e for e in sess.graph.edges
                      if e.src == "loop:0" and e.dst == "strat"]
        assert len(loop_edges) == 1
        # covered live links must NOT be lifted as explicit-port duplicates
        explicit = [e for e in sess.graph.edges
                    if e.src_port == "loopers:loop0_out_l"]
        assert explicit == []

    def test_capture_and_midi_links_lifted(self, tmp_path):
        sdir = tmp_path / "s"
        asyncio.run(do_save("s", sdir, SaveFakeOps()))
        sess = read_session(sdir)
        lifted = {(e.src_port, e.dst_port) for e in sess.graph.edges if e.src_port}
        assert (CAPTURE, "loopers:loop0_in_l") in lifted
        assert (CAPTURE, "loopers:loop0_in_r") in lifted
        assert (PACER, MIDI_IN) in lifted
        pacer_nodes = [n for n in sess.graph.nodes.values() if n.kind == "midi"]
        assert len(pacer_nodes) == 1
        assert "a2j" in sess.graph.runtime_units

    def test_nothing_running_is_failed(self, tmp_path):
        class DeadOps(SaveFakeOps):
            async def export_rig_state(self, chains_dir):
                return None
            async def looper_get_state(self):
                return None
            async def observe(self, graph):
                return ObservedState()
        report = asyncio.run(do_save("s", tmp_path / "s", DeadOps()))
        assert report.startswith("FAILED:")

    def test_missing_referenced_file_degrades(self, tmp_path):
        class NoChainOps(SaveFakeOps):
            async def export_rig_state(self, chains_dir):
                export = await super().export_rig_state(chains_dir)
                # simulate a child whose save failed: file never written
                Path(export["nodes"][1]["chain_file"]).unlink()
                return export
        report = asyncio.run(do_save("s", tmp_path / "s", NoChainOps()))
        assert report.startswith("DEGRADED:")
        assert "chains/strat.carxp" in report
