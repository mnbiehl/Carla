### Task 11: Converge engine — verified `do_stop`

**Files:**
- Modify: `source/frontend/carla_mcp/rig/converge.py` (append)
- Create: `source/frontend/carla_mcp/tests/test_rig_converge_stop.py`

**Interfaces:**
- Produces:
```python
DEFAULT_STOP_UNITS = [
    RuntimeUnit(name="carla:main", kind="carla-main"),
    RuntimeUnit(name="looper:mcp", kind="looper-mcp"),
    RuntimeUnit(name="looper:engine", kind="looper-engine"),
    RuntimeUnit(name="a2j", kind="a2j"),
]
async def do_stop(graph: Optional[RigGraph], ops: RigOps) -> str
```
- Stop order = reverse of `UNIT_START_ORDER`: carla-child → carla-main → looper-mcp → looper-engine → a2j. Uses `graph.runtime_units` when a graph is available, else `DEFAULT_STOP_UNITS`. After stopping, re-observes and reports any unit still up (`DEGRADED`). The optional pre-save is composed by the bridge tool (`save_as` → `do_save` first), not by `do_stop`.

**Steps:**

- [ ] Write failing test `tests/test_rig_converge_stop.py`:

```python
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
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_converge_stop.py -v` — expect `ImportError: cannot import name 'do_stop'`.
- [ ] Append to `rig/converge.py`:

```python
DEFAULT_STOP_UNITS = [
    RuntimeUnit(name="carla:main", kind="carla-main"),
    RuntimeUnit(name="looper:mcp", kind="looper-mcp"),
    RuntimeUnit(name="looper:engine", kind="looper-engine"),
    RuntimeUnit(name="a2j", kind="a2j"),
]


async def do_stop(graph: Optional[RigGraph], ops: RigOps) -> str:
    """Tear the rig down (children -> main Carla -> looper MCP -> looper
    engine -> a2j) and verify everything is actually dead."""
    if graph is not None and graph.runtime_units:
        units = list(graph.runtime_units.values())
        verify_graph = graph
    else:
        units = list(DEFAULT_STOP_UNITS)
        verify_graph = RigGraph()
        for u in units:
            verify_graph.add_runtime_unit(u)

    notes: List[str] = []
    stopped: List[str] = []
    for unit in sorted(units, key=lambda u: (-UNIT_START_ORDER.get(u.kind, 9), u.name)):
        err = await ops.stop_unit(unit)
        if err:
            notes.append(f"stop {unit.name}: {err}")
        else:
            stopped.append(unit.name)

    observed = await ops.observe(verify_graph)
    survivors = [name for name, up in observed.unit_status.items() if up]
    issues = notes + [f"still up after stop: {name}" for name in survivors]
    verdict = "OK" if not issues else f"DEGRADED: {len(issues)} issues"
    return render_report(verdict, [("Stopped", stopped), ("Issues", issues)])
```

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_converge_stop.py -v`
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/converge.py source/frontend/carla_mcp/tests/test_rig_converge_stop.py
git commit -m "feat(rig): verified do_stop teardown in reverse start order

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

