"""Tests for rig/graph.py — RigGraph, Node, Edge, Effect."""

import pytest

from carla_mcp.rig.graph import Effect, Node, Edge, RigGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _track(name: str, **kw) -> Node:
    return Node(name=name, kind="track", **kw)


def _bus(name: str, **kw) -> Node:
    return Node(name=name, kind="bus", **kw)


def _endpoint(name: str) -> Node:
    return Node(name=name, kind="endpoint")


def _effect(role: str, handle: str | None = None) -> Effect:
    h = handle if handle is not None else f"node/{role}"
    return Effect(handle=h, role=role, plugin=f"plugin_{role}")


# ---------------------------------------------------------------------------
# Node add/remove
# ---------------------------------------------------------------------------

class TestAddRemoveNode:
    def test_add_node(self):
        g = RigGraph()
        g.add_node(_track("strat"))
        assert g.has_node("strat")

    def test_get_node(self):
        g = RigGraph()
        g.add_node(_track("strat"))
        n = g.get_node("strat")
        assert n.name == "strat"

    def test_add_duplicate_raises(self):
        g = RigGraph()
        g.add_node(_track("strat"))
        with pytest.raises(ValueError, match="already exists"):
            g.add_node(_track("strat"))

    def test_has_node_false(self):
        g = RigGraph()
        assert not g.has_node("missing")

    def test_get_missing_raises(self):
        g = RigGraph()
        with pytest.raises(KeyError):
            g.get_node("missing")

    def test_remove_node(self):
        g = RigGraph()
        g.add_node(_track("strat"))
        g.remove_node("strat")
        assert not g.has_node("strat")

    def test_remove_missing_raises(self):
        g = RigGraph()
        with pytest.raises(KeyError):
            g.remove_node("missing")

    def test_remove_node_cleans_up_edges(self):
        """Removing a node must drop all edges that touch it."""
        g = RigGraph()
        g.add_node(_endpoint("in:guitar"))
        g.add_node(_track("strat"))
        g.add_node(_endpoint("out:main"))
        g.add_edge("in:guitar", "strat")
        g.add_edge("strat", "out:main")
        assert len(g.edges) == 2

        g.remove_node("strat")
        assert len(g.edges) == 0
        # The surviving nodes are unaffected
        assert g.has_node("in:guitar")
        assert g.has_node("out:main")


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

class TestEdges:
    def _graph_with_nodes(self) -> RigGraph:
        g = RigGraph()
        g.add_node(_endpoint("in:guitar"))
        g.add_node(_track("strat"))
        g.add_node(_endpoint("out:main"))
        g.add_node(_bus("reverb"))
        return g

    def test_add_edge(self):
        g = self._graph_with_nodes()
        g.add_edge("in:guitar", "strat")
        assert len(g.edges_from("in:guitar")) == 1
        assert g.edges_from("in:guitar")[0].dst == "strat"

    def test_add_edge_with_gain(self):
        g = self._graph_with_nodes()
        g.add_edge("in:guitar", "strat", gain_db=-6.0)
        edge = g.edges_from("in:guitar")[0]
        assert edge.gain_db == -6.0

    def test_add_edge_idempotent_updates_gain(self):
        """Adding the same edge again replaces gain_db; list stays length 1."""
        g = self._graph_with_nodes()
        g.add_edge("in:guitar", "strat", gain_db=0.0)
        g.add_edge("in:guitar", "strat", gain_db=-3.0)
        assert len(g.edges_from("in:guitar")) == 1
        assert g.edges_from("in:guitar")[0].gain_db == -3.0

    def test_add_edge_missing_src_raises(self):
        g = self._graph_with_nodes()
        with pytest.raises(KeyError, match="missing"):
            g.add_edge("missing", "strat")

    def test_add_edge_missing_dst_raises(self):
        g = self._graph_with_nodes()
        with pytest.raises(KeyError, match="missing"):
            g.add_edge("in:guitar", "missing")

    def test_edges_to(self):
        g = self._graph_with_nodes()
        g.add_edge("in:guitar", "strat")
        g.add_edge("strat", "out:main")
        assert len(g.edges_to("strat")) == 1
        assert g.edges_to("strat")[0].src == "in:guitar"
        assert len(g.edges_to("out:main")) == 1

    def test_remove_edge(self):
        g = self._graph_with_nodes()
        g.add_edge("in:guitar", "strat")
        g.remove_edge("in:guitar", "strat")
        assert len(g.edges_from("in:guitar")) == 0

    def test_remove_missing_edge_raises(self):
        g = self._graph_with_nodes()
        with pytest.raises(KeyError):
            g.remove_edge("in:guitar", "strat")

    def test_many_to_one(self):
        """Multiple sources can feed the same destination."""
        g = self._graph_with_nodes()
        g.add_node(Node(name="bass", kind="track"))
        g.add_edge("strat", "out:main")
        g.add_edge("bass", "out:main")
        assert len(g.edges_to("out:main")) == 2

    def test_one_to_many(self):
        """One source can feed multiple destinations."""
        g = self._graph_with_nodes()
        g.add_edge("in:guitar", "strat")
        g.add_edge("in:guitar", "reverb")
        assert len(g.edges_from("in:guitar")) == 2


# ---------------------------------------------------------------------------
# Effect chain — basic operations
# ---------------------------------------------------------------------------

class TestEffectChain:
    def _track_graph(self) -> RigGraph:
        g = RigGraph()
        g.add_node(_track("strat"))
        return g

    def test_add_effect_end(self):
        g = self._track_graph()
        g.add_effect("strat", _effect("comp"))
        g.add_effect("strat", _effect("reverb"))
        node = g.get_node("strat")
        assert [e.role for e in node.effects] == ["comp", "reverb"]

    def test_add_effect_start(self):
        g = self._track_graph()
        g.add_effect("strat", _effect("reverb"))
        g.add_effect("strat", _effect("comp"), position="start")
        node = g.get_node("strat")
        assert [e.role for e in node.effects] == ["comp", "reverb"]

    def test_add_effect_before_role(self):
        g = self._track_graph()
        g.add_effect("strat", _effect("comp"))
        g.add_effect("strat", _effect("reverb"))
        g.add_effect("strat", _effect("delay"), position="before:reverb")
        assert [e.role for e in g.get_node("strat").effects] == ["comp", "delay", "reverb"]

    def test_add_effect_after_role(self):
        g = self._track_graph()
        g.add_effect("strat", _effect("comp"))
        g.add_effect("strat", _effect("reverb"))
        g.add_effect("strat", _effect("delay"), position="after:comp")
        assert [e.role for e in g.get_node("strat").effects] == ["comp", "delay", "reverb"]

    def test_add_effect_by_index(self):
        g = self._track_graph()
        g.add_effect("strat", _effect("comp"))
        g.add_effect("strat", _effect("reverb"))
        g.add_effect("strat", _effect("delay"), position=1)
        assert [e.role for e in g.get_node("strat").effects] == ["comp", "delay", "reverb"]

    def test_add_effect_index_zero(self):
        g = self._track_graph()
        g.add_effect("strat", _effect("reverb"))
        g.add_effect("strat", _effect("comp"), position=0)
        assert [e.role for e in g.get_node("strat").effects] == ["comp", "reverb"]

    def test_add_effect_before_unknown_role_raises(self):
        g = self._track_graph()
        g.add_effect("strat", _effect("comp"))
        with pytest.raises(ValueError, match="'missing'"):
            g.add_effect("strat", _effect("delay"), position="before:missing")

    def test_add_effect_after_unknown_role_raises(self):
        g = self._track_graph()
        with pytest.raises(ValueError, match="'missing'"):
            g.add_effect("strat", _effect("delay"), position="after:missing")

    def test_add_effect_index_out_of_range_raises(self):
        g = self._track_graph()
        with pytest.raises(IndexError):
            g.add_effect("strat", _effect("comp"), position=5)

    def test_add_effect_on_endpoint_raises(self):
        g = RigGraph()
        g.add_node(_endpoint("in:guitar"))
        with pytest.raises(ValueError, match="endpoint"):
            g.add_effect("in:guitar", _effect("comp"))

    def test_add_effect_on_missing_node_raises(self):
        g = RigGraph()
        with pytest.raises(KeyError):
            g.add_effect("missing", _effect("comp"))

    def test_bus_supports_effects(self):
        g = RigGraph()
        g.add_node(_bus("reverb"))
        g.add_effect("reverb", _effect("verb"))
        assert len(g.get_node("reverb").effects) == 1

    def test_remove_effect_by_role(self):
        g = self._track_graph()
        g.add_effect("strat", _effect("comp"))
        g.add_effect("strat", _effect("reverb"))
        g.remove_effect("strat", "comp")
        assert [e.role for e in g.get_node("strat").effects] == ["reverb"]

    def test_remove_effect_by_handle(self):
        g = self._track_graph()
        eff = Effect(handle="strat/comp", role="comp", plugin="mcompressor")
        g.add_effect("strat", eff)
        g.remove_effect("strat", "strat/comp")
        assert g.get_node("strat").effects == []

    def test_remove_missing_effect_raises(self):
        g = self._track_graph()
        with pytest.raises(ValueError, match="'missing'"):
            g.remove_effect("strat", "missing")

    def test_find_effect_by_role(self):
        g = self._track_graph()
        eff = _effect("comp")
        g.add_effect("strat", eff)
        found = g.find_effect("strat", "comp")
        assert found is eff

    def test_find_effect_by_handle(self):
        g = self._track_graph()
        eff = Effect(handle="strat/comp", role="comp", plugin="mcompressor")
        g.add_effect("strat", eff)
        found = g.find_effect("strat", "strat/comp")
        assert found is eff

    def test_find_effect_missing_returns_none(self):
        g = self._track_graph()
        assert g.find_effect("strat", "nope") is None


# ---------------------------------------------------------------------------
# Effect chain — move
# ---------------------------------------------------------------------------

class TestMoveEffect:
    def _strat_with_chain(self) -> RigGraph:
        g = RigGraph()
        g.add_node(_track("strat"))
        g.add_effect("strat", _effect("comp"))
        g.add_effect("strat", _effect("delay"))
        g.add_effect("strat", _effect("reverb"))
        return g

    def _roles(self, g: RigGraph) -> list[str]:
        return [e.role for e in g.get_node("strat").effects]

    def test_move_to_end(self):
        g = self._strat_with_chain()
        g.move_effect("strat", "comp", "end")
        assert self._roles(g) == ["delay", "reverb", "comp"]

    def test_move_to_start(self):
        g = self._strat_with_chain()
        g.move_effect("strat", "reverb", "start")
        assert self._roles(g) == ["reverb", "comp", "delay"]

    def test_move_before(self):
        g = self._strat_with_chain()
        g.move_effect("strat", "reverb", "before:delay")
        assert self._roles(g) == ["comp", "reverb", "delay"]

    def test_move_after(self):
        g = self._strat_with_chain()
        g.move_effect("strat", "comp", "after:delay")
        assert self._roles(g) == ["delay", "comp", "reverb"]

    def test_move_by_index(self):
        g = self._strat_with_chain()
        g.move_effect("strat", "reverb", 0)
        assert self._roles(g) == ["reverb", "comp", "delay"]

    def test_move_by_handle(self):
        g = RigGraph()
        g.add_node(_track("strat"))
        eff_comp = Effect(handle="strat/comp", role="comp", plugin="mcomp")
        eff_rev = Effect(handle="strat/reverb", role="reverb", plugin="mrev")
        g.add_effect("strat", eff_comp)
        g.add_effect("strat", eff_rev)
        g.move_effect("strat", "strat/comp", "end")
        assert self._roles(g) == ["reverb", "comp"]

    def test_move_missing_raises(self):
        g = self._strat_with_chain()
        with pytest.raises(ValueError, match="'nope'"):
            g.move_effect("strat", "nope", "end")
