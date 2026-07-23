"""Tests for rig/reconcile.diff — the primary correctness surface."""

from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, ObservedState
from carla_mcp.rig.reconcile import LOOPER_MIDI_IN, diff

MON0 = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"
MON1 = "alsa_output.usb-F-00.pro-output-0:playback_AUX1"
PACER = "a2j:Pacer [32] (capture): Pacer MIDI 1"

OUTPUTS = ["loopers:loop0_out_l", "loopers:loop0_out_r",
           "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2", PACER]
INPUTS = ["loopers:loop0_in_l", "loopers:loop0_in_r",
          "CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
          LOOPER_MIDI_IN, MON0, MON1]

DESIRED_LINKS = [
    Link("loopers:loop0_out_l", "CarlaChain_strat:audio-in1"),
    Link("loopers:loop0_out_r", "CarlaChain_strat:audio-in2"),
    Link("CarlaChain_strat:audio-out1", MON0),
    Link("CarlaChain_strat:audio-out2", MON1),
    Link(PACER, LOOPER_MIDI_IN),
]


def _graph():
    g = RigGraph()
    g.add_node(Node(name="loop:0", kind="loop", port_index=0))
    g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat"))
    g.add_node(Node(name="out:main", kind="endpoint"))
    g.add_node(Node(name="app:looper", kind="app"))
    g.add_node(Node(name="midi:pacer", kind="midi", port_pattern=r"a2j:.*Pacer.*capture"))
    g.add_edge("loop:0", "strat")
    g.add_edge("strat", "out:main")
    g.add_edge("midi:pacer", "app:looper", kind="midi")
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
    g.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
    return g


def _observed(links=None, units_up=True, outputs=None, inputs=None, handles=None):
    status = {"carla:main": units_up, "carla:strat": units_up, "looper:engine": units_up}
    return ObservedState(
        links=list(DESIRED_LINKS if links is None else links),
        output_ports=OUTPUTS if outputs is None else outputs,
        input_ports=INPUTS if inputs is None else inputs,
        unit_status=status,
        instance_handles=handles or {},
    )


class TestCleanRig:
    def test_matching_rig_is_clean(self):
        d = diff(_graph(), _observed())
        assert d.is_clean
        assert d.verdict == "OK"
        assert d.issues() == []


class TestMissingEdges:
    def test_missing_connection_reported(self):
        links = [l for l in DESIRED_LINKS if l.dst != MON1]
        d = diff(_graph(), _observed(links=links))
        assert not d.is_clean
        assert any(p.dst == MON1 for p in d.missing_edges)
        assert d.verdict == "DEGRADED: 1 issues"

    def test_missing_midi_edge_reported(self):
        links = [l for l in DESIRED_LINKS if l.src != PACER]
        d = diff(_graph(), _observed(links=links))
        assert any(p.kind == "midi" for p in d.missing_edges)


class TestUnexpectedConnections:
    def test_stale_crossed_link_reported(self):
        stale = Link("loopers:loop0_out_r", "CarlaChain_strat:audio-in1")
        d = diff(_graph(), _observed(links=DESIRED_LINKS + [stale]))
        assert stale in d.unexpected_connections

    def test_non_rig_links_ignored(self):
        outside = Link("Firefox:output_FL", MON0)
        d = diff(_graph(), _observed(links=DESIRED_LINKS + [outside]))
        assert d.is_clean


class TestDownUnitsAndAbsence:
    def test_down_unit_reported(self):
        d = diff(_graph(), _observed(units_up=False))
        assert set(d.down_units) == {"carla:main", "carla:strat", "looper:engine"}

    def test_dead_child_yields_absent_node_and_dead_ports(self):
        outs = [p for p in OUTPUTS if "CarlaChain" not in p]
        ins = [p for p in INPUTS if "CarlaChain" not in p]
        links = [l for l in DESIRED_LINKS if "CarlaChain" not in l.src and "CarlaChain" not in l.dst]
        d = diff(_graph(), _observed(links=links, outputs=outs, inputs=ins))
        assert "strat" in d.absent_nodes
        assert any("strat" in m for m in d.dead_ports)
        assert "CarlaChain_strat:audio-in1" in d.waitable_ports


class TestUnresolvedEffects:
    def test_missing_handle_reported(self):
        g = _graph()
        from carla_mcp.rig.graph import Effect
        g.get_node("strat").effects.append(
            Effect(handle="strat/comp", role="comp", plugin="x42-comp"))
        d = diff(g, _observed(handles={"strat": {"0": "strat/eq"}}))
        assert d.unresolved_effects == ["strat: effect 'strat/comp' not resolved on child instance"]

    def test_present_handle_clean(self):
        g = _graph()
        from carla_mcp.rig.graph import Effect
        g.get_node("strat").effects.append(
            Effect(handle="strat/comp", role="comp", plugin="x42-comp"))
        d = diff(g, _observed(handles={"strat": {"0": "strat/comp"}}))
        assert d.unresolved_effects == []

    def test_unprobed_instance_not_flagged(self):
        """No handle snapshot for a node -> covered by unit status, not effects."""
        g = _graph()
        from carla_mcp.rig.graph import Effect
        g.get_node("strat").effects.append(
            Effect(handle="strat/comp", role="comp", plugin="x42-comp"))
        d = diff(g, _observed(handles={}))
        assert d.unresolved_effects == []


class TestIssuesFlattening:
    def test_every_category_appears_in_issues(self):
        stale = Link("loopers:loop0_out_r", "CarlaChain_strat:audio-in1")
        links = [l for l in DESIRED_LINKS if l.dst != MON1] + [stale]
        d = diff(_graph(), _observed(links=links, units_up=False))
        text = "\n".join(d.issues())
        assert "missing edge" in text
        assert "unexpected connection" in text
        assert "down unit" in text
        assert d.issue_count == len(d.issues())
