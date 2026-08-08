### Task 12: `observe()` I/O builder + Carla-side `rig_handles` tool

**Files:**
- Modify: `source/frontend/carla_mcp/rig/observe.py` (append `observe()`)
- Modify: `source/frontend/carla_mcp/rig/controller.py` (append `snapshot_handles` after `import_rig_state`, ~line 1241)
- Modify: `source/frontend/carla_mcp/rig/register.py` (add `rig_handles` tool after `import_rig_state`, ~line 302)
- Modify: `source/frontend/carla_mcp/tests/test_rig_register.py` (add `"rig_handles"` to `EXPECTED_TOOLS`, bump count 16→17 in `test_all_16_tools_are_registered`/`test_tool_count_is_exactly_16`)
- Create: `source/frontend/carla_mcp/tests/test_rig_observe_io.py`

**Interfaces:**
- Produces:
```python
# observe.py
async def observe(
    units: List[RuntimeUnit],
    *,
    list_links: Callable[[], List[Tuple[str, str]]],     # JackRouter().list_connections
    list_outputs: Callable[[], List[str]],               # pw_link_list_outputs
    list_inputs: Callable[[], List[str]],                # pw_link_list_inputs
    unit_probe: Callable[[RuntimeUnit], bool],
    looper_get_state: Optional[Callable[[], Awaitable[Optional[dict]]]] = None,
    carla_handles: Optional[Callable[[], Awaitable[Dict[str, Dict[str, str]]]]] = None,
) -> ObservedState

# controller.py
async def snapshot_handles(self) -> dict   # {"nodes": {node: {pid_str: handle}}, "errors": [...]}
```
- `rig_handles` MCP tool (main Carla) returns `controller.snapshot_handles()`; the bridge's `carla_handles` callable calls it over SSE and returns the `"nodes"` map.

**Steps:**

- [ ] Write failing test `tests/test_rig_observe_io.py`:

```python
"""Tests for observe() assembly and controller.snapshot_handles."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from carla_mcp.rig.controller import RigController
from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, observe


class TestObserve:
    def test_assembles_snapshot_from_callables(self):
        units = [RuntimeUnit(name="carla:main", kind="carla-main"),
                 RuntimeUnit(name="looper:engine", kind="looper-engine")]

        async def get_state():
            return {"loopers": []}

        async def get_handles():
            return {"strat": {"0": "strat/eq"}}

        obs = asyncio.run(observe(
            units,
            list_links=lambda: [("a:1", "b:1")],
            list_outputs=lambda: ["a:1"],
            list_inputs=lambda: ["b:1"],
            unit_probe=lambda u: u.kind == "carla-main",
            looper_get_state=get_state,
            carla_handles=get_handles,
        ))
        assert obs.links == [Link("a:1", "b:1")]
        assert obs.unit_status == {"carla:main": True, "looper:engine": False}
        assert obs.looper_state == {"loopers": []}
        assert obs.instance_handles == {"strat": {"0": "strat/eq"}}

    def test_probe_failures_never_raise(self):
        async def broken():
            raise ConnectionError("down")

        def broken_sync():
            raise OSError("pw gone")

        obs = asyncio.run(observe(
            [RuntimeUnit(name="a2j", kind="a2j")],
            list_links=broken_sync,
            list_outputs=broken_sync,
            list_inputs=broken_sync,
            unit_probe=lambda u: (_ for _ in ()).throw(OSError("boom")),
            looper_get_state=broken,
            carla_handles=broken,
        ))
        assert obs.links == [] and obs.output_ports == []
        assert obs.unit_status == {"a2j": False}
        assert obs.looper_state is None
        assert obs.instance_handles == {}


class TestSnapshotHandles:
    def test_collects_per_node_handles_and_errors(self):
        graph = RigGraph()
        graph.add_node(Node(name="strat", kind="track", instance="strat"))
        graph.add_node(Node(name="bass", kind="track", instance="bass"))
        graph.add_node(Node(name="in:guitar", kind="endpoint"))

        good = MagicMock()
        good.list_handles = AsyncMock(return_value={0: "strat/eq"})
        bad = MagicMock()
        bad.list_handles = AsyncMock(side_effect=RuntimeError("child dead"))

        def factory(node):
            return good if node.name == "strat" else bad

        controller = RigController(
            graph, MagicMock(), MagicMock(), MagicMock(),
            sleep=lambda *_: None, remote_factory=factory,
        )
        result = asyncio.run(controller.snapshot_handles())
        assert result["nodes"] == {"strat": {"0": "strat/eq"}}
        assert result["errors"] == ["bass: child dead"]
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_observe_io.py -v` — expect `ImportError: cannot import name 'observe'`.
- [ ] Append to `rig/observe.py` (add `from typing import Awaitable, Callable, Tuple` and `from carla_mcp.rig.graph import RuntimeUnit` to imports):

```python
async def observe(
    units: List["RuntimeUnit"],
    *,
    list_links: Callable[[], List[Tuple[str, str]]],
    list_outputs: Callable[[], List[str]],
    list_inputs: Callable[[], List[str]],
    unit_probe: Callable[["RuntimeUnit"], bool],
    looper_get_state: Optional[Callable[[], "Awaitable[Optional[dict]]"]] = None,
    carla_handles: Optional[Callable[[], "Awaitable[Dict[str, Dict[str, str]]]"]] = None,
) -> ObservedState:
    """Gather a full ObservedState through injected collaborators.

    Every probe is individually shielded: a failing collaborator yields an
    empty/False observation (which the diff then reports), never an exception.
    """
    def _safe_list(fn: Callable[[], list]) -> list:
        try:
            return list(fn())
        except Exception:  # noqa: BLE001 — observation must not raise
            return []

    status: Dict[str, bool] = {}
    for unit in units:
        try:
            status[unit.name] = bool(unit_probe(unit))
        except Exception:  # noqa: BLE001
            status[unit.name] = False

    looper_state = None
    if looper_get_state is not None:
        try:
            looper_state = await looper_get_state()
        except Exception:  # noqa: BLE001
            looper_state = None

    handles: Dict[str, Dict[str, str]] = {}
    if carla_handles is not None:
        try:
            handles = dict(await carla_handles() or {})
        except Exception:  # noqa: BLE001
            handles = {}

    return ObservedState(
        links=[Link(s, d) for s, d in _safe_list(list_links)],
        output_ports=_safe_list(list_outputs),
        input_ports=_safe_list(list_inputs),
        unit_status=status,
        looper_state=looper_state,
        instance_handles=handles,
    )
```

- [ ] Append `snapshot_handles` to `RigController` (controller.py, after `import_rig_state`):

```python
    async def snapshot_handles(self) -> dict:
        """Re-resolve every track/bus child's live plugin handles.

        Read-only observation surface for the reconciler: one list_handles
        round-trip per child.  Failures are reported per node, never raised.

        Returns:
            ``{"nodes": {node_name: {plugin_id_str: handle}}, "errors": [...]}``.
        """
        nodes: dict = {}
        errors: list[str] = []
        for node in list(self._graph.nodes.values()):
            if node.kind not in ("track", "bus"):
                continue
            try:
                handles = await self._remote(node).list_handles()
                nodes[node.name] = {str(pid): h for pid, h in handles.items()}
            except Exception as exc:  # noqa: BLE001 — report, don't abort
                errors.append(f"{node.name}: {exc}")
        return {"nodes": nodes, "errors": errors}
```

- [ ] Register the tool in `register.py` (insert before the probe-tools section):

```python
    @mcp.tool()
    async def rig_handles() -> dict:
        """Re-resolve live plugin handles on every track/bus child instance.

        Read-only. Returns ``{"nodes": {node: {plugin_id: handle}},
        "errors": [...]}``; used by the bridge's rig reconciler to verify
        that every saved effect still exists after a restore.
        """
        return await controller.snapshot_handles()
```

- [ ] Update `tests/test_rig_register.py`: add `"rig_handles"` to `EXPECTED_TOOLS`; change both count assertions from 16 to 17; in `_make_mcp_and_controller` add `controller.snapshot_handles = AsyncMock(return_value={"nodes": {}, "errors": []})`.
- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_observe_io.py source/frontend/carla_mcp/tests/test_rig_register.py -v`
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/observe.py source/frontend/carla_mcp/rig/controller.py source/frontend/carla_mcp/rig/register.py source/frontend/carla_mcp/tests/test_rig_observe_io.py source/frontend/carla_mcp/tests/test_rig_register.py
git commit -m "feat(rig): observe() I/O assembler and rig_handles observation tool

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

