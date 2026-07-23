"""Tests for rig/graph.py v3 extensions — loop/app/midi nodes, edge kinds, runtime units."""

import pytest

from carla_mcp.rig.graph import (
    EDGE_KINDS, NODE_KINDS, Edge, Node, RigGraph, RuntimeUnit,
)


class TestNodeKinds:
    def test_new_kinds_are_valid(self):
        g = RigGraph()
        g.add_node(Node(name="loop:0", kind="loop", looper_id=7, port_index=0))
        g.add_node(Node(name="app:looper", kind="app", main_muted=True))
        g.add_node(Node(name="midi:pacer", kind="midi", port_pattern=r"a2j:.*Pacer.*capture"))
        assert g.get_node("loop:0").looper_id == 7
        assert g.get_node("app:looper").main_muted is True
        assert g.get_node("midi:pacer").port_pattern.endswith("capture")

    def test_unknown_kind_rejected(self):
        g = RigGraph()
        with pytest.raises(ValueError, match="kind"):
            g.add_node(Node(name="x", kind="banana"))

    def test_node_kinds_constant(self):
        assert NODE_KINDS == ("endpoint", "track", "bus", "loop", "app", "midi")

    def test_track_node_chain_file_field(self):
        n = Node(name="strat", kind="track", chain_file="chains/strat.carxp")
        assert n.chain_file == "chains/strat.carxp"


class TestEdgeKinds:
    def test_default_edge_kind_is_audio(self):
        g = RigGraph()
        g.add_node(Node(name="a", kind="endpoint"))
        g.add_node(Node(name="b", kind="endpoint"))
        g.add_edge("a", "b")
        assert g.edges[0].kind == "audio"

    def test_midi_edge_kind(self):
        g = RigGraph()
        g.add_node(Node(name="midi:pacer", kind="midi"))
        g.add_node(Node(name="app:looper", kind="app"))
        g.add_edge("midi:pacer", "app:looper", kind="midi")
        assert g.edges[0].kind == "midi"

    def test_bad_edge_kind_rejected(self):
        g = RigGraph()
        g.add_node(Node(name="a", kind="endpoint"))
        g.add_node(Node(name="b", kind="endpoint"))
        with pytest.raises(ValueError, match="kind"):
            g.add_edge("a", "b", kind="quantum")

    def test_edge_kinds_constant(self):
        assert EDGE_KINDS == ("audio", "midi")


class TestExplicitPortEdges:
    def test_explicit_port_edges_are_distinct(self):
        """Two edges between the same node pair with different explicit ports coexist."""
        g = RigGraph()
        g.add_node(Node(name="cap", kind="endpoint", jack_client="alsa_input.x:capture_AUX0"))
        g.add_node(Node(name="loop:0", kind="loop", port_index=0))
        g.add_edge("cap", "loop:0", src_port="alsa_input.x:capture_AUX0",
                   dst_port="loopers:loop0_in_l")
        g.add_edge("cap", "loop:0", src_port="alsa_input.x:capture_AUX0",
                   dst_port="loopers:loop0_in_r")
        assert len(g.edges) == 2

    def test_same_ports_edge_is_idempotent(self):
        g = RigGraph()
        g.add_node(Node(name="a", kind="endpoint"))
        g.add_node(Node(name="b", kind="endpoint"))
        g.add_edge("a", "b", gain_db=0.0, src_port="a:1", dst_port="b:1")
        g.add_edge("a", "b", gain_db=-3.0, src_port="a:1", dst_port="b:1")
        assert len(g.edges) == 1
        assert g.edges[0].gain_db == -3.0

    def test_node_level_edge_still_idempotent(self):
        g = RigGraph()
        g.add_node(Node(name="a", kind="endpoint"))
        g.add_node(Node(name="b", kind="endpoint"))
        g.add_edge("a", "b")
        g.add_edge("a", "b", gain_db=-6.0)
        assert len(g.edges) == 1
        assert g.edges[0].gain_db == -6.0


class TestRuntimeUnits:
    def test_add_runtime_unit(self):
        g = RigGraph()
        g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
        g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
        assert set(g.runtime_units) == {"carla:main", "carla:strat"}
        assert g.runtime_units["carla:strat"].node == "strat"

    def test_add_runtime_unit_replaces_by_name(self):
        g = RigGraph()
        g.add_runtime_unit(RuntimeUnit(name="a2j", kind="a2j"))
        g.add_runtime_unit(RuntimeUnit(name="a2j", kind="a2j", node="x"))
        assert len(g.runtime_units) == 1
        assert g.runtime_units["a2j"].node == "x"

    def test_remove_node_keeps_runtime_units(self):
        """Runtime-unit expectations are separate from port connectivity/nodes."""
        g = RigGraph()
        g.add_node(Node(name="strat", kind="track"))
        g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
        g.remove_node("strat")
        assert "carla:strat" in g.runtime_units
