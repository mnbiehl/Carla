"""Tests for rig/converge.do_stop — verified teardown in reverse start order."""

import asyncio

from carla_mcp.rig.converge import RigOps, do_stop
from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import ObservedState


def _graph():
    g = RigGraph()
    g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat"))
    g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    g.add_runtime_unit(RuntimeUnit(name="looper:mcp", kind="looper-mcp"))
    g.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
    g.add_runtime_unit(RuntimeUnit(name="a2j", kind="a2j"))
    return g


class StopFakeOps(RigOps):
    def __init__(self, stubborn=()):
        self.units_up = {"carla:strat", "carla:main", "looper:mcp",
                         "looper:engine", "a2j"}
        self.stubborn = set(stubborn)
        self.stopped = []

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph else []
        return ObservedState(unit_status={u.name: u.name in self.units_up
                                          for u in units})

    async def stop_unit(self, unit):
        self.stopped.append(unit.name)
        if unit.name in self.stubborn:
            return "refused to die"
        self.units_up.discard(unit.name)
        return None


class TestDoStop:
    def test_stops_in_reverse_start_order(self):
        ops = StopFakeOps()
        report = asyncio.run(do_stop(_graph(), ops))
        assert ops.stopped == ["carla:strat", "carla:main", "looper:mcp",
                               "looper:engine", "a2j"]
        assert report.splitlines()[0] == "OK"

    def test_survivor_degrades_verdict(self):
        ops = StopFakeOps(stubborn={"looper:engine"})
        report = asyncio.run(do_stop(_graph(), ops))
        assert report.startswith("DEGRADED:")
        assert "looper:engine" in report

    def test_no_graph_uses_default_units(self):
        ops = StopFakeOps()
        report = asyncio.run(do_stop(None, ops))
        assert "carla:main" in ops.stopped
        assert "looper:engine" in ops.stopped
        assert report.splitlines()[0] == "OK"
