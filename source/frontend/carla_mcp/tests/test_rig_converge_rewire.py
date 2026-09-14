"""Tests for rig/converge.do_rewire — links-only rewire to the desired graph."""

import asyncio

from carla_mcp.rig.converge import RigOps, do_rewire
from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, ObservedState

MON0 = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"
MON1 = "alsa_output.usb-F-00.pro-output-0:playback_AUX1"

OUTPUTS = ["loopers:loop0_out_l", "loopers:loop0_out_r", "loopers:loop1_out_l",
           "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2", "Firefox:output_FL"]
INPUTS = ["CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2", "Carla:audio-in3",
          "loopers:loop0_in_l", "loopers:loop0_in_r", MON0, MON1]

DESIRED_PRESENT = ("loopers:loop0_out_l", "CarlaChain_strat:audio-in1")
STRAY = ("loopers:loop1_out_l", "Carla:audio-in3")          # rig space, not wanted
DESKTOP = ("Firefox:output_FL", MON0)                        # outside rig space
MISSING = [("loopers:loop0_out_r", "CarlaChain_strat:audio-in2"),
           ("CarlaChain_strat:audio-out1", MON0),
           ("CarlaChain_strat:audio-out2", MON1)]


def _graph():
    g = RigGraph()
    g.add_node(Node(name="loop:0", kind="loop", port_index=0))
    g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat"))
    g.add_node(Node(name="out:main", kind="endpoint"))
    g.add_edge("loop:0", "strat")
    g.add_edge("strat", "out:main")
    return g


class RewireFakeOps(RigOps):
    """Links-only world. Every non-link side effect fails the test if reached."""

    def __init__(self, links, fail_connect=()):
        self.links = set(links)
        self.fail_connect = set(fail_connect)
        self.calls = []

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph else []
        return ObservedState(links=[Link(s, d) for s, d in sorted(self.links)],
                             output_ports=list(OUTPUTS), input_ports=list(INPUTS),
                             unit_status={u.name: False for u in units})

    def connect(self, src, dst):
        self.calls.append(("connect", src, dst))
        if (src, dst) in self.fail_connect:
            return "device busy"
        self.links.add((src, dst))
        return None

    def disconnect(self, src, dst):
        self.calls.append(("disconnect", src, dst))
        self.links.discard((src, dst))
        return None

    def _forbidden(self, *args, **kwargs):
        raise AssertionError("do_rewire must only connect/disconnect")

    start_unit = stop_unit = load_carla_project = import_rig_state = _forbidden
    load_looper_session = set_looper_mutes = wait_ports = _forbidden


def _world():
    return RewireFakeOps({DESIRED_PRESENT, STRAY, DESKTOP})


def test_dry_run_plans_disconnects_then_connects_and_changes_nothing():
    ops = _world()
    rw = asyncio.run(do_rewire(_graph(), ops, dry_run=True))
    assert [(a.op, a.src, a.dst) for a in rw.planned] == (
        [("disconnect", *STRAY)] + [("connect", s, d) for s, d in MISSING])
    assert ops.calls == [] and ops.links == {DESIRED_PRESENT, STRAY, DESKTOP}
    assert rw.applied == [] and rw.failures == []


def test_rewire_removes_stray_rig_link_connects_missing_and_leaves_desktop_link():
    ops = _world()
    rw = asyncio.run(do_rewire(_graph(), ops))
    assert ops.links == {DESIRED_PRESENT, DESKTOP, *MISSING}
    assert ("disconnect", *DESKTOP) not in ops.calls
    assert [(a.op, a.src, a.dst) for a in rw.applied] == [(a.op, a.src, a.dst) for a in rw.planned]
    assert rw.failures == [] and rw.diff.is_clean
    report = rw.report()
    assert report.splitlines()[0] == "OK"
    assert f"  {STRAY[0]} -> {STRAY[1]}" in report and "[Connected]" in report


def test_already_wired_rig_is_a_no_op():
    ops = RewireFakeOps({DESIRED_PRESENT, DESKTOP, *MISSING})
    rw = asyncio.run(do_rewire(_graph(), ops))
    assert rw.planned == [] and ops.calls == [] and rw.report() == "OK"


def test_failed_connect_is_a_failure_and_the_post_diff_is_degraded():
    ops = RewireFakeOps({DESIRED_PRESENT, STRAY, DESKTOP}, fail_connect={MISSING[1]})
    rw = asyncio.run(do_rewire(_graph(), ops))
    assert rw.failures == [f"connect {MISSING[1][0]} -> {MISSING[1][1]}: device busy"]
    assert len(rw.applied) == len(rw.planned) - 1
    assert rw.diff.verdict == "DEGRADED: 1 issues"
    assert rw.diff.issues() == [f"missing edge: {MISSING[1][0]} -> {MISSING[1][1]} (audio)"]
    assert "[Failures]" in rw.report()


def test_down_units_and_absent_nodes_are_reported_never_started_or_waited_for():
    g = _graph()
    g.add_node(Node(name="loop:2", kind="loop", port_index=2))   # no ports: absent, waitable
    g.add_runtime_unit(RuntimeUnit(name="a2j", kind="a2j"))        # observed down
    ops = _world()
    dry = asyncio.run(do_rewire(g, ops, dry_run=True))
    assert {a.op for a in dry.planned} == {"disconnect", "connect"}
    assert dry.unfixable == ["absent node: loop:2", "down unit: a2j"]
    rw = asyncio.run(do_rewire(g, ops))   # _forbidden raises on start_unit / wait_ports
    assert rw.diff.issues() == ["absent node: loop:2", "down unit: a2j"]
    assert rw.diff.verdict == "DEGRADED: 2 issues" and rw.failures == []
