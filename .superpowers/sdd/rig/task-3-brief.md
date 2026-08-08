### Task 3: Pure port expansion + rig-port-space predicate (`rig/reconcile.py` part 1)

**Files:**
- Create: `source/frontend/carla_mcp/rig/reconcile.py`
- Create: `source/frontend/carla_mcp/tests/test_rig_reconcile_expand.py`

**Interfaces:**
- Produces (all pure, no I/O):
```python
LOOPER_MIDI_IN = "loopers:loopers_midi_in"

@dataclass(frozen=True)
class PortPair:
    src: str
    dst: str
    kind: str = "audio"

def resolve_stereo_ports(base: str, available: List[str]) -> List[str]
def make_port_pairs(src_ports, dst_ports) -> List[Tuple[str, str]]
def node_output_ports(node: Node, live_outputs: List[str]) -> List[str]
def node_input_ports(node: Node, live_inputs: List[str]) -> List[str]
def canonical_ports(node: Node) -> List[str]           # waitable even when absent

@dataclass
class Expansion:
    pairs: List[PortPair]
    dead_ports: List[str]        # human messages, one per unresolvable edge
    absent_nodes: List[str]
    waitable_ports: List[str]

def expand_edges(graph: RigGraph, live_outputs, live_inputs) -> Expansion
def in_rig_port_space(src: str, dst: str) -> bool
```
- Consumes: `RigGraph`, `Node`, `Edge` (Task 1). Stereo pairing rules identical to `RigController._make_port_pairs` (controller.py:245–264) and resolution rules identical to `_resolve_stereo_ports` (controller.py:141–164).

**Steps:**

- [ ] Write failing test `tests/test_rig_reconcile_expand.py`:

```python
"""Tests for rig/reconcile.py port expansion — the pure desired-state surface."""

from carla_mcp.rig.graph import Node, RigGraph
from carla_mcp.rig.reconcile import (
    LOOPER_MIDI_IN, PortPair, canonical_ports, expand_edges,
    in_rig_port_space, make_port_pairs, node_input_ports, node_output_ports,
    resolve_stereo_ports,
)

MONITORS = [
    "alsa_output.usb-Focusrite-00.pro-output-0:playback_AUX0",
    "alsa_output.usb-Focusrite-00.pro-output-0:playback_AUX1",
]
CAPTURE = "alsa_input.usb-Focusrite-00.pro-input-0:capture_AUX0"


def _rig():
    """loop:0 -> strat (track) -> out:main, capture -> loop:0, pacer midi -> looper."""
    g = RigGraph()
    g.add_node(Node(name="loop:0", kind="loop", looper_id=7, port_index=0))
    g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat"))
    g.add_node(Node(name="out:main", kind="endpoint"))
    g.add_node(Node(name="in:guitar", kind="endpoint", jack_client=CAPTURE))
    g.add_node(Node(name="app:looper", kind="app"))
    g.add_node(Node(name="midi:pacer", kind="midi", port_pattern=r"a2j:.*Pacer.*capture"))
    g.add_edge("loop:0", "strat")
    g.add_edge("strat", "out:main")
    g.add_edge("in:guitar", "loop:0")
    g.add_edge("midi:pacer", "app:looper", kind="midi")
    return g


LIVE_OUTPUTS = [
    "loopers:loop0_out_l", "loopers:loop0_out_r",
    "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2",
    CAPTURE,
    "a2j:Pacer [32] (capture): Pacer MIDI 1",
]
LIVE_INPUTS = [
    "loopers:loop0_in_l", "loopers:loop0_in_r",
    "CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
    LOOPER_MIDI_IN,
] + MONITORS


class TestPortRules:
    def test_resolve_l_r_suffix(self):
        avail = ["x_l", "x_r", "y"]
        assert resolve_stereo_ports("x", avail) == ["x_l", "x_r"]

    def test_resolve_numeric_suffix(self):
        assert resolve_stereo_ports("x", ["x1", "x2"]) == ["x1", "x2"]

    def test_resolve_mono(self):
        assert resolve_stereo_ports("y", ["y"]) == ["y"]

    def test_resolve_none(self):
        assert resolve_stereo_ports("z", ["a"]) == []

    def test_pairs_stereo_straight(self):
        assert make_port_pairs(["l", "r"], ["L", "R"]) == [("l", "L"), ("r", "R")]

    def test_pairs_mono_fanout(self):
        assert make_port_pairs(["m"], ["L", "R"]) == [("m", "L"), ("m", "R")]

    def test_pairs_stereo_sum(self):
        assert make_port_pairs(["l", "r"], ["M"]) == [("l", "M"), ("r", "M")]


class TestNodePorts:
    def test_loop_output_ports(self):
        n = Node(name="loop:0", kind="loop", port_index=0)
        assert node_output_ports(n, LIVE_OUTPUTS) == ["loopers:loop0_out_l", "loopers:loop0_out_r"]

    def test_loop_input_ports(self):
        n = Node(name="loop:0", kind="loop", port_index=0)
        assert node_input_ports(n, LIVE_INPUTS) == ["loopers:loop0_in_l", "loopers:loop0_in_r"]

    def test_track_ports_filtered_to_live(self):
        n = Node(name="strat", kind="track", jack_client="CarlaChain_strat")
        assert node_output_ports(n, []) == []
        assert node_output_ports(n, LIVE_OUTPUTS) == [
            "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2"]

    def test_app_input_is_midi_in(self):
        n = Node(name="app:looper", kind="app")
        assert node_input_ports(n, LIVE_INPUTS) == [LOOPER_MIDI_IN]

    def test_midi_node_matches_pattern(self):
        n = Node(name="midi:pacer", kind="midi", port_pattern=r"a2j:.*Pacer.*capture")
        assert node_output_ports(n, LIVE_OUTPUTS) == ["a2j:Pacer [32] (capture): Pacer MIDI 1"]

    def test_out_main_resolves_monitor_regex(self):
        n = Node(name="out:main", kind="endpoint")
        assert node_input_ports(n, LIVE_INPUTS) == MONITORS

    def test_canonical_ports_track(self):
        n = Node(name="strat", kind="track", jack_client="CarlaChain_strat")
        assert canonical_ports(n) == [
            "CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
            "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2"]

    def test_canonical_ports_loop(self):
        n = Node(name="loop:2", kind="loop", port_index=2)
        assert canonical_ports(n) == [
            "loopers:loop2_in_l", "loopers:loop2_in_r",
            "loopers:loop2_out_l", "loopers:loop2_out_r"]


class TestExpandEdges:
    def test_full_rig_expands_to_expected_pairs(self):
        exp = expand_edges(_rig(), LIVE_OUTPUTS, LIVE_INPUTS)
        pairs = {(p.src, p.dst) for p in exp.pairs}
        assert ("loopers:loop0_out_l", "CarlaChain_strat:audio-in1") in pairs
        assert ("loopers:loop0_out_r", "CarlaChain_strat:audio-in2") in pairs
        assert ("CarlaChain_strat:audio-out1", MONITORS[0]) in pairs
        assert ("CarlaChain_strat:audio-out2", MONITORS[1]) in pairs
        # mono capture fans out to both loop inputs
        assert (CAPTURE, "loopers:loop0_in_l") in pairs
        assert (CAPTURE, "loopers:loop0_in_r") in pairs
        assert ("a2j:Pacer [32] (capture): Pacer MIDI 1", LOOPER_MIDI_IN) in pairs
        assert exp.dead_ports == [] and exp.absent_nodes == []

    def test_midi_pair_carries_midi_kind(self):
        exp = expand_edges(_rig(), LIVE_OUTPUTS, LIVE_INPUTS)
        midi = [p for p in exp.pairs if p.kind == "midi"]
        assert midi == [PortPair("a2j:Pacer [32] (capture): Pacer MIDI 1", LOOPER_MIDI_IN, "midi")]

    def test_dead_track_reports_absent_and_dead_ports(self):
        outs = [p for p in LIVE_OUTPUTS if "CarlaChain" not in p]
        ins = [p for p in LIVE_INPUTS if "CarlaChain" not in p]
        exp = expand_edges(_rig(), outs, ins)
        assert "strat" in exp.absent_nodes
        assert any("strat" in m for m in exp.dead_ports)
        assert "CarlaChain_strat:audio-in1" in exp.waitable_ports

    def test_explicit_port_edge_bypasses_expansion(self):
        g = RigGraph()
        g.add_node(Node(name="cap", kind="endpoint", jack_client=CAPTURE))
        g.add_node(Node(name="loop:0", kind="loop", port_index=0))
        g.add_edge("cap", "loop:0", src_port=CAPTURE, dst_port="loopers:loop0_in_r")
        exp = expand_edges(g, [CAPTURE], ["loopers:loop0_in_l", "loopers:loop0_in_r"])
        assert exp.pairs == [PortPair(CAPTURE, "loopers:loop0_in_r", "audio")]

    def test_explicit_port_edge_dead_when_port_missing(self):
        g = RigGraph()
        g.add_node(Node(name="cap", kind="endpoint", jack_client=CAPTURE))
        g.add_node(Node(name="loop:0", kind="loop", port_index=0))
        g.add_edge("cap", "loop:0", src_port=CAPTURE, dst_port="loopers:loop0_in_r")
        exp = expand_edges(g, [CAPTURE], [])
        assert exp.pairs == []
        assert any("loopers:loop0_in_r" in m for m in exp.dead_ports)
        assert "loopers:loop0_in_r" in exp.waitable_ports


class TestRigPortSpace:
    def test_loopers_to_carla_in_space(self):
        assert in_rig_port_space("loopers:loop0_out_l", "Carla:audio-in3")

    def test_chain_to_hardware_in_space(self):
        assert in_rig_port_space("CarlaChain_strat:audio-out1", MONITORS[0])

    def test_hardware_to_loopers_in_space(self):
        assert in_rig_port_space(CAPTURE, "loopers:loop0_in_l")

    def test_midi_into_looper_in_space(self):
        assert in_rig_port_space("a2j:Pacer [32] (capture): Pacer MIDI 1", LOOPER_MIDI_IN)

    def test_unrelated_apps_untouched(self):
        assert not in_rig_port_space("Firefox:output_FL", MONITORS[0])
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_reconcile_expand.py -v` — expect `ModuleNotFoundError: No module named 'carla_mcp.rig.reconcile'`.
- [ ] Implement `rig/reconcile.py`:

```python
"""
Pure diff/plan engine for the rig reconciler.

NO I/O in this module — no subprocess, no sockets, no clock.  Everything
operates on a desired RigGraph and an ObservedState snapshot so the whole
correctness surface is unit-testable against fabricated states.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from carla_mcp.rig.graph import Node, RigGraph
from carla_mcp.rig.observe import Link, ObservedState

LOOPER_MIDI_IN = "loopers:loopers_midi_in"

# Same hardware-monitor shape as utils/pw_link.py:137 — duplicated here (two
# lines of regex) so this module stays import-light and pure.
_MONITOR_INPUT_RE = re.compile(r"^alsa_output\..*pro-output.*:playback_AUX\d+$")

_RIG_CLIENT_RE = re.compile(r"^(Carla|CarlaChain_[^:]+|loopers):")


@dataclass(frozen=True)
class PortPair:
    """One concrete desired connection between two live ports."""

    src: str
    dst: str
    kind: str = "audio"


def resolve_stereo_ports(base: str, available: List[str]) -> List[str]:
    """Resolve a port base to concrete ports: _l/_r, then 1/2, then mono."""
    available_set = set(available)
    if f"{base}_l" in available_set and f"{base}_r" in available_set:
        return [f"{base}_l", f"{base}_r"]
    if f"{base}1" in available_set and f"{base}2" in available_set:
        return [f"{base}1", f"{base}2"]
    if base in available_set:
        return [base]
    return []


def make_port_pairs(
    src_ports: List[str], dst_ports: List[str]
) -> List[Tuple[str, str]]:
    """Pair ports by the rig's mono/stereo rules (L->L R->R; fan-out; sum)."""
    n_src, n_dst = len(src_ports), len(dst_ports)
    if n_src == 0 or n_dst == 0:
        return []
    if n_src == 2 and n_dst == 2:
        return [(src_ports[0], dst_ports[0]), (src_ports[1], dst_ports[1])]
    if n_src == 1 and n_dst == 2:
        return [(src_ports[0], dst_ports[0]), (src_ports[0], dst_ports[1])]
    if n_src == 2 and n_dst == 1:
        return [(src_ports[0], dst_ports[0]), (src_ports[1], dst_ports[0])]
    return [(src_ports[0], dst_ports[0])]


def node_output_ports(node: Node, live_outputs: List[str]) -> List[str]:
    """Live output ports for *node* (only ports that actually exist)."""
    live = set(live_outputs)
    if node.kind in ("track", "bus"):
        want = [f"{node.jack_client}:audio-out1", f"{node.jack_client}:audio-out2"]
        return [p for p in want if p in live]
    if node.kind == "loop":
        want = [f"loopers:loop{node.port_index}_out_l",
                f"loopers:loop{node.port_index}_out_r"]
        return [p for p in want if p in live]
    if node.kind == "midi":
        if not node.port_pattern:
            return []
        rx = re.compile(node.port_pattern)
        return sorted(p for p in live_outputs if rx.search(p))
    if node.kind == "app":
        return []
    return resolve_stereo_ports(node.jack_client or node.name, live_outputs)


def node_input_ports(node: Node, live_inputs: List[str]) -> List[str]:
    """Live input ports for *node* (only ports that actually exist)."""
    live = set(live_inputs)
    if node.kind in ("track", "bus"):
        want = [f"{node.jack_client}:audio-in1", f"{node.jack_client}:audio-in2"]
        return [p for p in want if p in live]
    if node.kind == "loop":
        want = [f"loopers:loop{node.port_index}_in_l",
                f"loopers:loop{node.port_index}_in_r"]
        return [p for p in want if p in live]
    if node.kind == "app":
        return [LOOPER_MIDI_IN] if LOOPER_MIDI_IN in live else []
    if node.kind == "midi":
        return []
    if node.name == "out:main" and not node.jack_client:
        return sorted(p for p in live_inputs if _MONITOR_INPUT_RE.match(p))[:2]
    return resolve_stereo_ports(node.jack_client or node.name, live_inputs)


def canonical_ports(node: Node) -> List[str]:
    """Port names knowable without live state — what we can wait for."""
    if node.kind in ("track", "bus") and node.jack_client:
        c = node.jack_client
        return [f"{c}:audio-in1", f"{c}:audio-in2", f"{c}:audio-out1", f"{c}:audio-out2"]
    if node.kind == "loop":
        n = node.port_index
        return [f"loopers:loop{n}_in_l", f"loopers:loop{n}_in_r",
                f"loopers:loop{n}_out_l", f"loopers:loop{n}_out_r"]
    if node.kind == "app":
        return [LOOPER_MIDI_IN]
    return []


@dataclass
class Expansion:
    """Result of expanding node-level edges into concrete port pairs."""

    pairs: List[PortPair] = field(default_factory=list)
    dead_ports: List[str] = field(default_factory=list)
    absent_nodes: List[str] = field(default_factory=list)
    waitable_ports: List[str] = field(default_factory=list)


def expand_edges(
    graph: RigGraph, live_outputs: List[str], live_inputs: List[str]
) -> Expansion:
    """Expand every desired edge to live port pairs; name what can't resolve."""
    exp = Expansion()
    live_all = set(live_outputs) | set(live_inputs)

    for node in graph.nodes.values():
        outs = node_output_ports(node, live_outputs)
        ins = node_input_ports(node, live_inputs)
        if not outs and not ins:
            exp.absent_nodes.append(node.name)
            exp.waitable_ports.extend(canonical_ports(node))

    for edge in graph.edges:
        if edge.src_port and edge.dst_port:
            missing = [p for p in (edge.src_port, edge.dst_port) if p not in live_all]
            if missing:
                exp.dead_ports.append(
                    f"edge {edge.src} -> {edge.dst}: port(s) not live: "
                    + ", ".join(missing)
                )
                exp.waitable_ports.extend(missing)
            else:
                exp.pairs.append(PortPair(edge.src_port, edge.dst_port, edge.kind))
            continue
        src_ports = node_output_ports(graph.get_node(edge.src), live_outputs)
        dst_ports = node_input_ports(graph.get_node(edge.dst), live_inputs)
        if not src_ports or not dst_ports:
            side = edge.src if not src_ports else edge.dst
            exp.dead_ports.append(
                f"edge {edge.src} -> {edge.dst}: no live ports for '{side}'"
            )
            continue
        for s, d in make_port_pairs(src_ports, dst_ports):
            exp.pairs.append(PortPair(s, d, edge.kind))
    return exp


def in_rig_port_space(src: str, dst: str) -> bool:
    """True when a connection touches rig-owned port space.

    Rig port space is any connection with at least one endpoint on Carla,
    a CarlaChain_* child, or the loopers engine (audio or MIDI).  Unrelated
    desktop audio never matches and is never touched.
    """
    return bool(_RIG_CLIENT_RE.match(src) or _RIG_CLIENT_RE.match(dst))
```

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_reconcile_expand.py -v`
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/reconcile.py source/frontend/carla_mcp/tests/test_rig_reconcile_expand.py
git commit -m "feat(rig): pure port expansion and rig-port-space predicate

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

