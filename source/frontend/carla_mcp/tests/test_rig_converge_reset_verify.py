"""Tests for rig/converge.py — routing reset and read-only verify."""

import asyncio

from carla_mcp.rig.converge import RigOps, do_routing_reset, do_verify
from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, ObservedState


class FakeOps(RigOps):
    def __init__(self, links, outputs=(), inputs=(), units_up=()):
        self.links = set(links)
        self.outputs = list(outputs)
        self.inputs = list(inputs)
        self.units_up = set(units_up)
        self.disconnected = []

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph else []
        return ObservedState(
            links=[Link(s, d) for s, d in sorted(self.links)],
            output_ports=self.outputs,
            input_ports=self.inputs,
            unit_status={u.name: u.name in self.units_up for u in units},
        )

    def disconnect(self, src, dst):
        if (src, dst) not in self.links:
            return "no such link"
        self.links.discard((src, dst))
        self.disconnected.append((src, dst))
        return None


MON = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"


class TestRoutingReset:
    def test_clears_only_rig_space(self):
        ops = FakeOps(links={
            ("loopers:loop0_out_l", "Carla:audio-in3"),
            ("CarlaChain_strat:audio-out1", MON),
            ("Firefox:output_FL", MON),
        })
        report = asyncio.run(do_routing_reset(ops))
        assert report.splitlines()[0] == "OK"
        assert ("Firefox:output_FL", MON) in ops.links
        assert len(ops.disconnected) == 2

    def test_failed_disconnect_degrades_verdict(self):
        class StubbornOps(FakeOps):
            def disconnect(self, src, dst):
                return "device busy"
        ops = StubbornOps(links={("loopers:loop0_out_l", "Carla:audio-in3")})
        report = asyncio.run(do_routing_reset(ops))
        assert report.splitlines()[0] == "DEGRADED: 1 issues"
        assert "device busy" in report

    def test_nothing_to_clear_is_ok(self):
        report = asyncio.run(do_routing_reset(FakeOps(links=set())))
        assert report.splitlines()[0] == "OK"


class TestVerify:
    def _graph(self):
        g = RigGraph()
        g.add_node(Node(name="loop:0", kind="loop", port_index=0))
        g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat"))
        g.add_edge("loop:0", "strat")
        g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
        return g

    def test_clean_rig_verifies_ok(self):
        ops = FakeOps(
            links={("loopers:loop0_out_l", "CarlaChain_strat:audio-in1"),
                   ("loopers:loop0_out_r", "CarlaChain_strat:audio-in2")},
            outputs=["loopers:loop0_out_l", "loopers:loop0_out_r",
                     "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2"],
            inputs=["CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
                    "loopers:loop0_in_l", "loopers:loop0_in_r"],
            units_up={"carla:strat"},
        )
        report = asyncio.run(do_verify(self._graph(), ops))
        assert report.splitlines()[0] == "OK"

    def test_broken_rig_names_every_issue(self):
        ops = FakeOps(links=set(), outputs=[], inputs=[], units_up=set())
        report = asyncio.run(do_verify(self._graph(), ops))
        assert report.startswith("DEGRADED:")
        assert "down unit: carla:strat" in report
        assert "absent node:" in report
