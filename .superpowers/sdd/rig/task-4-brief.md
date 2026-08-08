### Task 4: `diff(desired, observed)` (`rig/reconcile.py` part 2)

**Files:**
- Modify: `source/frontend/carla_mcp/rig/reconcile.py` (append)
- Create: `source/frontend/carla_mcp/tests/test_rig_reconcile_diff.py`

**Interfaces:**
- Produces:
```python
@dataclass
class RigDiff:
    missing_edges: List[PortPair]
    unexpected_connections: List[Link]
    absent_nodes: List[str]
    down_units: List[str]
    dead_ports: List[str]
    unresolved_effects: List[str]
    waitable_ports: List[str]
    def issues(self) -> List[str]           # flat, prefixed, report-ready
    @property def issue_count(self) -> int
    @property def is_clean(self) -> bool
    @property def verdict(self) -> str      # "OK" | "DEGRADED: <n> issues"

def diff(graph: RigGraph, observed: ObservedState) -> RigDiff
```
- Consumes: `Expansion`/`expand_edges` (Task 3), `ObservedState` (Task 2), `graph.runtime_units` (Task 1). `waitable_ports` is not counted as a separate issue category (it mirrors dead ports/absent nodes for planning).

**Steps:**

- [ ] Write failing test `tests/test_rig_reconcile_diff.py`:

```python
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
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_reconcile_diff.py -v` — expect `ImportError: cannot import name 'diff'`.
- [ ] Append to `rig/reconcile.py`:

```python
@dataclass
class RigDiff:
    """Named deviations between desired graph and observed reality."""

    missing_edges: List[PortPair] = field(default_factory=list)
    unexpected_connections: List[Link] = field(default_factory=list)
    absent_nodes: List[str] = field(default_factory=list)
    down_units: List[str] = field(default_factory=list)
    dead_ports: List[str] = field(default_factory=list)
    unresolved_effects: List[str] = field(default_factory=list)
    waitable_ports: List[str] = field(default_factory=list)

    def issues(self) -> List[str]:
        """Every deviation as a report-ready line. Nothing summarized away."""
        out: List[str] = []
        out += [f"missing edge: {p.src} -> {p.dst} ({p.kind})" for p in self.missing_edges]
        out += [f"unexpected connection: {l.src} -> {l.dst}" for l in self.unexpected_connections]
        out += [f"absent node: {n}" for n in self.absent_nodes]
        out += [f"down unit: {u}" for u in self.down_units]
        out += [f"dead port reference: {m}" for m in self.dead_ports]
        out += [f"unresolved effect: {m}" for m in self.unresolved_effects]
        return out

    @property
    def issue_count(self) -> int:
        return len(self.issues())

    @property
    def is_clean(self) -> bool:
        return self.issue_count == 0

    @property
    def verdict(self) -> str:
        return "OK" if self.is_clean else f"DEGRADED: {self.issue_count} issues"


def diff(graph: RigGraph, observed: ObservedState) -> RigDiff:
    """Pure structural diff between the desired graph and observed state."""
    exp = expand_edges(graph, observed.output_ports, observed.input_ports)
    live = {(l.src, l.dst) for l in observed.links}
    want = {(p.src, p.dst) for p in exp.pairs}

    missing = [p for p in exp.pairs if (p.src, p.dst) not in live]
    unexpected = [
        l for l in observed.links
        if (l.src, l.dst) not in want and in_rig_port_space(l.src, l.dst)
    ]
    down = [
        u.name for u in graph.runtime_units.values()
        if not observed.unit_status.get(u.name, False)
    ]
    unresolved: List[str] = []
    for node in graph.nodes.values():
        if node.kind not in ("track", "bus") or not node.effects:
            continue
        handles = observed.instance_handles.get(node.name)
        if handles is None:
            continue  # instance not probed; its liveness is covered by unit status
        have = set(handles.values())
        for eff in node.effects:
            if eff.handle not in have:
                unresolved.append(
                    f"{node.name}: effect '{eff.handle}' not resolved on child instance"
                )

    return RigDiff(
        missing_edges=missing,
        unexpected_connections=unexpected,
        absent_nodes=exp.absent_nodes,
        down_units=down,
        dead_ports=exp.dead_ports,
        unresolved_effects=unresolved,
        waitable_ports=sorted(set(exp.waitable_ports)),
    )
```

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_reconcile_diff.py source/frontend/carla_mcp/tests/test_rig_reconcile_expand.py -v`
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/reconcile.py source/frontend/carla_mcp/tests/test_rig_reconcile_diff.py
git commit -m "feat(rig): pure diff engine over desired graph vs observed state

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

