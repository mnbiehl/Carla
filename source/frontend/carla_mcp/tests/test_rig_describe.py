"""Tests for rig/describe.py — describe_rig."""

import pytest

from carla_mcp.rig.graph import Effect, Node, RigGraph
from carla_mcp.rig.describe import describe_rig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _effect(role: str, bypassed: bool = False) -> Effect:
    return Effect(handle=f"node/{role}", role=role, plugin=f"plugin_{role}", bypassed=bypassed)


def _build_full_graph() -> RigGraph:
    """Strat + vocals + reverb example from the design doc."""
    g = RigGraph()
    g.add_node(Node(name="in:guitar", kind="endpoint"))
    g.add_node(Node(name="in:mic", kind="endpoint"))
    g.add_node(Node(name="out:main", kind="endpoint"))
    g.add_node(Node(
        name="strat",
        kind="track",
        effects=[_effect("comp"), _effect("amp")],
    ))
    g.add_node(Node(
        name="vocals",
        kind="track",
        effects=[_effect("gate"), _effect("comp")],
    ))
    g.add_node(Node(
        name="reverb",
        kind="bus",
        effects=[_effect("verb")],
    ))
    # Edges
    g.add_edge("in:guitar", "strat")
    g.add_edge("strat", "out:main")
    g.add_edge("strat", "reverb", gain_db=-12.0)
    g.add_edge("in:mic", "vocals")
    g.add_edge("vocals", "out:main")
    g.add_edge("vocals", "reverb", gain_db=-9.0)
    g.add_edge("reverb", "out:main")
    return g


# ---------------------------------------------------------------------------
# Full example
# ---------------------------------------------------------------------------

class TestDescribeFullGraph:
    def setup_method(self):
        self.graph = _build_full_graph()
        self.result = describe_rig(self.graph)

    def test_routing_section_present(self):
        assert "ROUTING" in self.result

    def test_chains_section_present(self):
        assert "CHAINS" in self.result

    def test_routing_before_chains(self):
        assert self.result.index("ROUTING") < self.result.index("CHAINS")

    def test_strat_to_main(self):
        assert "strat → out:main" in self.result

    def test_strat_to_reverb_with_gain(self):
        assert "strat → reverb (-12 dB)" in self.result

    def test_vocals_to_reverb_with_gain(self):
        assert "vocals → reverb (-9 dB)" in self.result

    def test_strat_chain(self):
        assert "strat: comp ▸ amp (loop: dry)" in self.result

    def test_reverb_chain(self):
        assert "reverb: verb" in self.result

    def test_reverb_chain_no_loop_dry(self):
        # reverb is a bus — should NOT have (loop: dry)
        assert "reverb: verb (loop: dry)" not in self.result

    def test_vocals_chain(self):
        assert "vocals: gate ▸ comp (loop: dry)" in self.result


# ---------------------------------------------------------------------------
# Empty graph
# ---------------------------------------------------------------------------

class TestDescribeEmptyGraph:
    def setup_method(self):
        self.result = describe_rig(RigGraph())

    def test_no_routes(self):
        assert "(no routes)" in self.result

    def test_no_chains(self):
        assert "(no chains)" in self.result

    def test_routing_before_chains(self):
        assert self.result.index("ROUTING") < self.result.index("CHAINS")


# ---------------------------------------------------------------------------
# Track with no effects
# ---------------------------------------------------------------------------

class TestTrackNoEffects:
    def test_no_effects_with_loop_dry(self):
        g = RigGraph()
        g.add_node(Node(name="bare", kind="track", effects=[]))
        result = describe_rig(g)
        assert "bare: (no effects) (loop: dry)" in result


# ---------------------------------------------------------------------------
# Bus with no effects
# ---------------------------------------------------------------------------

class TestBusNoEffects:
    def test_no_effects_no_loop_dry(self):
        g = RigGraph()
        g.add_node(Node(name="fx", kind="bus", effects=[]))
        result = describe_rig(g)
        assert "fx: (no effects)" in result
        assert "(loop: dry)" not in result


# ---------------------------------------------------------------------------
# Bypassed effect
# ---------------------------------------------------------------------------

class TestBypassedEffect:
    def test_bypassed_renders_with_star(self):
        g = RigGraph()
        g.add_node(Node(
            name="strat",
            kind="track",
            effects=[_effect("comp", bypassed=True), _effect("amp")],
        ))
        result = describe_rig(g)
        assert "comp*" in result

    def test_active_effect_no_star(self):
        g = RigGraph()
        g.add_node(Node(
            name="strat",
            kind="track",
            effects=[_effect("comp", bypassed=False)],
        ))
        result = describe_rig(g)
        assert "comp*" not in result
        assert "comp" in result


# ---------------------------------------------------------------------------
# Gain formatting
# ---------------------------------------------------------------------------

class TestGainFormatting:
    def test_unity_gain_no_suffix(self):
        g = RigGraph()
        g.add_node(Node(name="a", kind="track"))
        g.add_node(Node(name="b", kind="track"))
        g.add_edge("a", "b", gain_db=0.0)
        result = describe_rig(g)
        assert "a → b" in result
        assert "dB" not in result

    def test_nonzero_gain_has_suffix(self):
        g = RigGraph()
        g.add_node(Node(name="a", kind="track"))
        g.add_node(Node(name="b", kind="track"))
        g.add_edge("a", "b", gain_db=3.5)
        result = describe_rig(g)
        assert "a → b (3.5 dB)" in result

    def test_negative_gain_has_suffix(self):
        g = RigGraph()
        g.add_node(Node(name="a", kind="track"))
        g.add_node(Node(name="b", kind="track"))
        g.add_edge("a", "b", gain_db=-6.0)
        result = describe_rig(g)
        assert "a → b (-6 dB)" in result


# ---------------------------------------------------------------------------
# Only endpoints (no chains section body)
# ---------------------------------------------------------------------------

class TestOnlyEndpoints:
    def test_no_chains_when_only_endpoints(self):
        g = RigGraph()
        g.add_node(Node(name="in:guitar", kind="endpoint"))
        g.add_node(Node(name="out:main", kind="endpoint"))
        result = describe_rig(g)
        assert "(no chains)" in result
