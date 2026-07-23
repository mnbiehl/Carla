"""Tests for rig/converge.do_load — clean-slate, converge, verify, one retry."""

import asyncio
import json
from pathlib import Path

from carla_mcp.rig.converge import RigOps, do_load, rig_state_for_import
from carla_mcp.rig.graph import Node, RigGraph
from carla_mcp.rig.observe import Link, ObservedState
from carla_mcp.rig.session import RigSession, write_session

MON0 = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"
MON1 = "alsa_output.usb-F-00.pro-output-0:playback_AUX1"


def _write_v3_session(tmp_path) -> Path:
    g = RigGraph()
    g.add_node(Node(name="loop:0", kind="loop", looper_id=7, port_index=0))
    g.add_node(Node(name="strat", kind="track", instance="strat",
                    jack_client="CarlaChain_strat", source="loop:0",
                    chain_file="chains/strat.carxp"))
    g.add_node(Node(name="out:main", kind="endpoint"))
    g.add_node(Node(name="app:looper", kind="app", main_muted=True))
    g.add_edge("loop:0", "strat")
    g.add_edge("strat", "out:main")
    from carla_mcp.rig.graph import RuntimeUnit
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
    g.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
    g.add_runtime_unit(RuntimeUnit(name="looper:mcp", kind="looper-mcp"))
    sdir = tmp_path / "rt"
    (sdir / "chains").mkdir(parents=True)
    (sdir / "looper").mkdir()
    (sdir / "carla_project.carxp").write_text("<carla/>")
    (sdir / "chains" / "strat.carxp").write_text("<carla/>")
    (sdir / "looper" / "project.loopers").write_text(json.dumps({"loopers": []}))
    write_session(RigSession(name="rt", graph=g, carla_project="carla_project.carxp",
                             looper_session_dir="looper"), sdir)
    return sdir


class LoadFakeOps(RigOps):
    """Cold world: no units up, no ports, one stale link; start_unit brings ports."""

    def __init__(self):
        self.units_up = set()
        self.outputs = set()
        self.inputs = set([MON0, MON1])
        self.links = {("loopers:loop0_out_l", "Carla:audio-in1")}  # stale garbage
        self.calls = []

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph else []
        return ObservedState(
            links=[Link(s, d) for s, d in sorted(self.links)],
            output_ports=sorted(self.outputs),
            input_ports=sorted(self.inputs),
            unit_status={u.name: u.name in self.units_up for u in units},
        )

    async def start_unit(self, unit):
        self.calls.append(("start_unit", unit.name))
        self.units_up.add(unit.name)
        if unit.kind == "looper-engine":
            self.outputs |= {"loopers:loop0_out_l", "loopers:loop0_out_r"}
            self.inputs |= {"loopers:loop0_in_l", "loopers:loop0_in_r",
                            "loopers:loopers_midi_in"}
        return None

    def connect(self, src, dst):
        if src not in self.outputs or dst not in self.inputs:
            return f"port missing: {src} or {dst}"
        self.links.add((src, dst))
        return None

    def disconnect(self, src, dst):
        self.links.discard((src, dst))
        return None

    def wait_ports(self, ports, timeout_s=15.0):
        return [p for p in ports if p not in self.outputs | self.inputs]

    async def load_carla_project(self, path):
        self.calls.append(("load_carla_project", path))
        return None

    async def import_rig_state(self, state, chains_dir):
        self.calls.append(("import_rig_state", [n["name"] for n in state["nodes"]]))
        # respawning children makes their ports appear
        for n in state["nodes"]:
            if n["kind"] in ("track", "bus"):
                c = n["jack_client"]
                self.outputs |= {f"{c}:audio-out1", f"{c}:audio-out2"}
                self.inputs |= {f"{c}:audio-in1", f"{c}:audio-in2"}
        return {"success": True, "tracks": [], "messages": []}

    async def load_looper_session(self, project_path):
        self.calls.append(("load_looper_session", project_path))
        return None

    async def set_looper_mutes(self, main_muted, all_muted):
        self.calls.append(("set_looper_mutes", main_muted, all_muted))
        return None


class TestDoLoad:
    def test_cold_load_converges_to_ok(self, tmp_path):
        sdir = _write_v3_session(tmp_path)
        ops = LoadFakeOps()
        report = asyncio.run(do_load("rt", sdir, ops))
        assert report.splitlines()[0] == "OK", report
        # stale link clean-slated
        assert ("loopers:loop0_out_l", "Carla:audio-in1") not in ops.links
        # desired wiring present, L->L R->R
        assert ("loopers:loop0_out_l", "CarlaChain_strat:audio-in1") in ops.links
        assert ("loopers:loop0_out_r", "CarlaChain_strat:audio-in2") in ops.links
        assert ("CarlaChain_strat:audio-out1", MON0) in ops.links
        assert ("CarlaChain_strat:audio-out2", MON1) in ops.links

    def test_units_started_in_order(self, tmp_path):
        sdir = _write_v3_session(tmp_path)
        ops = LoadFakeOps()
        asyncio.run(do_load("rt", sdir, ops))
        starts = [c[1] for c in ops.calls if c[0] == "start_unit"]
        assert starts == ["looper:engine", "looper:mcp", "carla:main", "carla:strat"]

    def test_payload_restored_with_mutes(self, tmp_path):
        sdir = _write_v3_session(tmp_path)
        ops = LoadFakeOps()
        asyncio.run(do_load("rt", sdir, ops))
        names = [c[0] for c in ops.calls]
        assert "load_carla_project" in names
        assert "import_rig_state" in names
        assert ("set_looper_mutes", True, False) in ops.calls
        looper_calls = [c for c in ops.calls if c[0] == "load_looper_session"]
        assert looper_calls[0][1].endswith("looper/project.loopers")

    def test_missing_session_is_failed_verdict(self, tmp_path):
        report = asyncio.run(do_load("nope", tmp_path / "nope", LoadFakeOps()))
        assert report.startswith("FAILED:")

    def test_import_state_has_no_edges_and_translated_sources(self, tmp_path):
        sdir = _write_v3_session(tmp_path)
        from carla_mcp.rig.session import read_session
        sess = read_session(sdir)
        state = rig_state_for_import(sess.graph, sdir)
        assert state["edges"] == []
        strat = [n for n in state["nodes"] if n["name"] == "strat"][0]
        assert strat["source"] == "loopers:loop0_out"
        assert strat["chain_file"] == str(sdir / "chains" / "strat.carxp")
        # loop/app/midi nodes are not Carla-land nodes
        assert all(n["kind"] in ("endpoint", "track", "bus") for n in state["nodes"])
