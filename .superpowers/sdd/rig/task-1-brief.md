### Task 1: Graph model v3 — new node kinds, edge kinds, explicit ports, runtime units

**Files:**
- Modify: `source/frontend/carla_mcp/rig/graph.py` (Node dataclass lines 33–51, Edge dataclass lines 54–65, `RigGraph.__init__` line 75, `add_edge` lines 123–139)
- Create: `source/frontend/carla_mcp/tests/test_rig_graph_v3.py`

**Interfaces:**
- Produces: `NODE_KINDS = ("endpoint", "track", "bus", "loop", "app", "midi")`, `EDGE_KINDS = ("audio", "midi")`
- `Node` gains fields: `looper_id: Optional[int] = None`, `port_index: Optional[int] = None`, `main_muted: bool = False`, `all_muted: bool = False`, `port_pattern: Optional[str] = None`, `chain_file: Optional[str] = None`
- `Edge` gains fields: `kind: str = "audio"`, `src_port: Optional[str] = None`, `dst_port: Optional[str] = None`
- New `RuntimeUnit` dataclass: `name: str`, `kind: str` (one of `"carla-main" | "carla-child" | "looper-engine" | "looper-mcp" | "a2j"`), `node: Optional[str] = None`
- `RigGraph.runtime_units: dict[str, RuntimeUnit]`, `RigGraph.add_runtime_unit(unit)` (idempotent replace)
- `RigGraph.add_edge(src, dst, gain_db=0.0, kind="audio", src_port=None, dst_port=None)` — uniqueness key becomes `(src, dst, src_port, dst_port)`; validates `kind`
- `RigGraph.add_node` validates `node.kind in NODE_KINDS`

**Steps:**

- [ ] Write the failing test file `tests/test_rig_graph_v3.py`:

```python
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
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_graph_v3.py -v` — expect `ImportError: cannot import name 'RuntimeUnit'` (and `NODE_KINDS`/`EDGE_KINDS`).
- [ ] Implement in `rig/graph.py`. Add after the imports (line 12):

```python
NODE_KINDS = ("endpoint", "track", "bus", "loop", "app", "midi")
EDGE_KINDS = ("audio", "midi")
```

Extend `Node` (append after `effects` field, keeping existing docstring and adding to it):

```python
    # v3 whole-rig fields
    looper_id: Optional[int] = None      # loop nodes: engine looper id (volatile-ish, data only)
    port_index: Optional[int] = None     # loop nodes: N in loopers:loopN_{in,out}_{l,r}
    main_muted: bool = False             # app:looper only
    all_muted: bool = False              # app:looper only
    port_pattern: Optional[str] = None   # midi nodes: regex matched against live ports
    chain_file: Optional[str] = None     # track/bus: session-relative .carxp pointer
```

Extend `Edge`:

```python
@dataclass
class Edge:
    """A directed edge from one node to another.

    src/dst   — node names.
    gain_db   — gain applied on this connection, in dB (0.0 = unity).
    kind      — "audio" or "midi".
    src_port/dst_port — when both set, this edge binds these exact ports
                (used by the migrator and link-lifting; bypasses stereo
                expansion in the reconciler).
    """

    src: str
    dst: str
    gain_db: float = 0.0
    kind: str = "audio"
    src_port: Optional[str] = None
    dst_port: Optional[str] = None
```

Add `RuntimeUnit`:

```python
@dataclass
class RuntimeUnit:
    """A process the rig expects to be alive, independent of port wiring.

    name — stable unit name: "carla:main", "carla:<node>", "looper:engine",
           "looper:mcp", "a2j".
    kind — "carla-main" | "carla-child" | "looper-engine" | "looper-mcp" | "a2j".
    node — owning graph node name for carla-child units (else None).
    """

    name: str
    kind: str
    node: Optional[str] = None
```

In `RigGraph.__init__` add `self.runtime_units: dict[str, RuntimeUnit] = {}`. In `add_node` insert before the duplicate check:

```python
        if node.kind not in NODE_KINDS:
            raise ValueError(f"Unknown node kind '{node.kind}' for node '{node.name}'")
```

Replace `add_edge`:

```python
    def add_edge(
        self,
        src: str,
        dst: str,
        gain_db: float = 0.0,
        kind: str = "audio",
        src_port: Optional[str] = None,
        dst_port: Optional[str] = None,
    ) -> None:
        """Add (or update) an edge from *src* to *dst*.

        Uniqueness key is (src, dst, src_port, dst_port): node-level edges
        stay unique per node pair; explicit-port edges are unique per port
        pair, so a stereo lift can record two edges between the same nodes.

        Raises:
            KeyError:   if either node does not exist.
            ValueError: if *kind* is not a valid edge kind.
        """
        if kind not in EDGE_KINDS:
            raise ValueError(f"Unknown edge kind '{kind}'")
        if src not in self.nodes:
            raise KeyError(f"Source node '{src}' not found")
        if dst not in self.nodes:
            raise KeyError(f"Destination node '{dst}' not found")
        for edge in self.edges:
            if (edge.src, edge.dst, edge.src_port, edge.dst_port) == (src, dst, src_port, dst_port):
                edge.gain_db = gain_db
                edge.kind = kind
                return
        self.edges.append(
            Edge(src=src, dst=dst, gain_db=gain_db, kind=kind,
                 src_port=src_port, dst_port=dst_port)
        )

    def add_runtime_unit(self, unit: RuntimeUnit) -> None:
        """Register (or replace) a runtime-unit expectation by name."""
        self.runtime_units[unit.name] = unit
```

Also add `RuntimeUnit`, `NODE_KINDS`, `EDGE_KINDS` to `rig/__init__.py` imports and `__all__`.

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_graph_v3.py source/frontend/carla_mcp/tests/test_rig_graph.py source/frontend/carla_mcp/tests/test_rig_controller.py -v` (existing graph/controller tests must stay green).
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/graph.py source/frontend/carla_mcp/rig/__init__.py source/frontend/carla_mcp/tests/test_rig_graph_v3.py
git commit -m "feat(rig): extend graph model with loop/app/midi nodes, edge kinds, runtime units

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

