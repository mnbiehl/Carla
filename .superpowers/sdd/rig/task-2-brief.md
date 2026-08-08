### Task 2: Observed-state data model (`rig/observe.py`, pure part)

**Files:**
- Create: `source/frontend/carla_mcp/rig/observe.py`
- Create: `source/frontend/carla_mcp/tests/test_rig_observe_model.py`

**Interfaces:**
- Produces:
```python
@dataclass(frozen=True)
class Link:
    src: str
    dst: str

@dataclass
class ObservedState:
    links: List[Link] = field(default_factory=list)
    output_ports: List[str] = field(default_factory=list)
    input_ports: List[str] = field(default_factory=list)
    unit_status: Dict[str, bool] = field(default_factory=dict)
    looper_state: Optional[dict] = None
    instance_handles: Dict[str, Dict[str, str]] = field(default_factory=dict)  # node -> {plugin_id: handle}

def is_midi_port(name: str) -> bool
def loop_nodes_from_looper_state(state: Optional[dict]) -> List[Node]
```
- Consumes: `Node` from `rig/graph.py`; looper `GetState` shape per Rust contract (`"loopers": [{"id", "port_index", "mode", "level_db", "pan", "input_source"}]`).

**Steps:**

- [ ] Write failing test `tests/test_rig_observe_model.py`:

```python
"""Tests for rig/observe.py data model — Link, ObservedState, loop discovery."""

from carla_mcp.rig.observe import (
    Link, ObservedState, is_midi_port, loop_nodes_from_looper_state,
)


class TestLink:
    def test_link_is_hashable(self):
        assert {Link("a:1", "b:1"), Link("a:1", "b:1")} == {Link("a:1", "b:1")}


class TestIsMidiPort:
    def test_a2j_port_is_midi(self):
        assert is_midi_port("a2j:PACER MIDI [40] (capture): PACER MIDI MIDI 1")

    def test_loopers_midi_in_is_midi(self):
        assert is_midi_port("loopers:loopers_midi_in")

    def test_audio_port_is_not_midi(self):
        assert not is_midi_port("loopers:loop0_out_l")
        assert not is_midi_port("Carla:audio-in1")


class TestLoopDiscovery:
    def test_loops_discovered_from_getstate(self):
        state = {
            "loopers": [
                {"id": 7, "port_index": 0, "mode": "Playing", "level_db": 0.0,
                 "pan": 0.0, "input_source": None},
                {"id": 3, "port_index": 1, "mode": "Recording", "level_db": -6.0,
                 "pan": 1.0, "input_source": None},
            ]
        }
        nodes = loop_nodes_from_looper_state(state)
        assert [n.name for n in nodes] == ["loop:0", "loop:1"]
        assert nodes[0].kind == "loop"
        assert nodes[0].looper_id == 7
        assert nodes[1].port_index == 1

    def test_none_state_yields_no_loops(self):
        assert loop_nodes_from_looper_state(None) == []

    def test_legacy_getstate_without_loopers_key(self):
        assert loop_nodes_from_looper_state({"tempo": 120}) == []

    def test_looper_entry_without_port_index_skipped(self):
        state = {"loopers": [{"id": 1}]}
        assert loop_nodes_from_looper_state(state) == []


class TestObservedState:
    def test_defaults_are_empty(self):
        o = ObservedState()
        assert o.links == [] and o.unit_status == {} and o.looper_state is None
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_observe_model.py -v` — expect `ModuleNotFoundError: No module named 'carla_mcp.rig.observe'`.
- [ ] Implement `rig/observe.py` (pure part; the `observe()` I/O builder is Task 12):

```python
"""
Observed rig state: what is actually live on PipeWire, in the looper engine,
and in each managed process.

This module's data types are pure; `observe()` (added separately) gathers a
snapshot through injected callables so the bridge supplies real I/O and tests
supply fabricated state.  stdlib-only: this package is imported by the main
Carla process running system Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from carla_mcp.rig.graph import Node


@dataclass(frozen=True)
class Link:
    """One live pw-link connection (source port -> destination port)."""

    src: str
    dst: str


@dataclass
class ObservedState:
    """Snapshot of live rig reality, consumed by the pure diff engine.

    links            — every live pw connection (audio and midi).
    output_ports     — all live output port names (pw-link -o).
    input_ports      — all live input port names (pw-link -i).
    unit_status      — runtime-unit name -> is it up?
    looper_state     — raw GetState payload (contains "loopers": [...]), or None.
    instance_handles — track/bus node name -> {plugin_id_str: handle} re-resolved
                       from each child Carla instance.
    """

    links: List[Link] = field(default_factory=list)
    output_ports: List[str] = field(default_factory=list)
    input_ports: List[str] = field(default_factory=list)
    unit_status: Dict[str, bool] = field(default_factory=dict)
    looper_state: Optional[dict] = None
    instance_handles: Dict[str, Dict[str, str]] = field(default_factory=dict)


def is_midi_port(name: str) -> bool:
    """Best-effort port classification: a2j-bridged or 'midi'-named ports."""
    return name.startswith("a2j:") or "midi" in name.lower()


def loop_nodes_from_looper_state(state: Optional[dict]) -> List[Node]:
    """Build loop:N nodes from a GetState payload's per-looper summary.

    Loop nodes are auto-discovered, never hand-created: name is
    "loop:<port_index>" (the positional index N in loopers:loopN_* ports);
    the engine looper id rides along as data.  Entries without a port_index
    (pre-contract engines) are skipped — callers report that as degraded.
    """
    nodes: List[Node] = []
    for entry in (state or {}).get("loopers", []) or []:
        idx = entry.get("port_index")
        if idx is None:
            continue
        nodes.append(
            Node(name=f"loop:{idx}", kind="loop",
                 looper_id=entry.get("id"), port_index=idx)
        )
    nodes.sort(key=lambda n: n.port_index)
    return nodes
```

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_observe_model.py -v`
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/observe.py source/frontend/carla_mcp/tests/test_rig_observe_model.py
git commit -m "feat(rig): add ObservedState data model and looper loop discovery

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

