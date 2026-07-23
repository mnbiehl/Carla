"""Tests for rig/reconcile.plan and render_report — ordered fix actions."""

from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link
from carla_mcp.rig.reconcile import (
    Action, PortPair, RigDiff, UNIT_START_ORDER, plan, render_report,
)


def _graph_with_units():
    g = RigGraph()
    g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat"))
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
    g.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
    g.add_runtime_unit(RuntimeUnit(name="looper:mcp", kind="looper-mcp"))
    g.add_runtime_unit(RuntimeUnit(name="a2j", kind="a2j"))
    return g


class TestPlanOrdering:
    def test_processes_then_waits_then_disconnects_then_connects(self):
        d = RigDiff(
            missing_edges=[PortPair("a:1", "b:1")],
            unexpected_connections=[Link("x:1", "y:1")],
            down_units=["carla:strat", "looper:engine", "carla:main", "a2j", "looper:mcp"],
            waitable_ports=["CarlaChain_strat:audio-in1"],
        )
        actions = plan(d, _graph_with_units())
        ops = [a.op for a in actions]
        assert ops == ["start_unit"] * 5 + ["wait_ports", "disconnect", "connect"]

    def test_unit_start_order(self):
        d = RigDiff(down_units=["carla:strat", "looper:engine", "carla:main",
                                "a2j", "looper:mcp"])
        actions = plan(d, _graph_with_units())
        assert [a.unit for a in actions] == [
            "looper:engine", "looper:mcp", "a2j", "carla:main", "carla:strat"]

    def test_every_missing_edge_gets_a_connect(self):
        d = RigDiff(missing_edges=[PortPair("a:1", "b:1"), PortPair("a:2", "b:2", "midi")])
        actions = plan(d, _graph_with_units())
        connects = [a for a in actions if a.op == "connect"]
        assert {(a.src, a.dst, a.kind) for a in connects} == {
            ("a:1", "b:1", "audio"), ("a:2", "b:2", "midi")}

    def test_no_wait_action_when_nothing_waitable(self):
        actions = plan(RigDiff(), _graph_with_units())
        assert actions == []

    def test_wait_ports_deduped_and_sorted(self):
        d = RigDiff(waitable_ports=["b:1", "a:1", "b:1"])
        actions = plan(d, _graph_with_units())
        assert actions == [Action(op="wait_ports", ports=("a:1", "b:1"))]

    def test_unknown_down_unit_still_yields_action(self):
        """A unit named in the diff but absent from the graph must not vanish."""
        d = RigDiff(down_units=["ghost:unit"])
        actions = plan(d, _graph_with_units())
        assert actions == [Action(op="start_unit", unit="ghost:unit")]


class TestRenderReport:
    def test_verdict_is_first_line(self):
        report = render_report("DEGRADED: 2 issues",
                               [("Issues", ["missing edge: a -> b"])])
        assert report.splitlines()[0] == "DEGRADED: 2 issues"

    def test_empty_sections_omitted(self):
        report = render_report("OK", [("Issues", []), ("Notes", ["saved 3 files"])])
        assert "[Issues]" not in report
        assert "[Notes]" in report and "  saved 3 files" in report
