### Task 8: Converge engine — `RigOps` interface, `do_routing_reset`, `do_verify` (`rig/converge.py`)

**Files:**
- Create: `source/frontend/carla_mcp/rig/converge.py`
- Create: `source/frontend/carla_mcp/tests/test_rig_converge_reset_verify.py`

**Interfaces:**
- Produces:
```python
class RigOps:
    """Side-effect interface. The bridge implements it; tests fake it.
    All methods return None on success or an error string (never raise for
    expected failures), except observe/export/get_state which return data."""
    async def observe(self, graph: Optional[RigGraph]) -> ObservedState
    async def start_unit(self, unit: RuntimeUnit) -> Optional[str]
    async def stop_unit(self, unit: RuntimeUnit) -> Optional[str]
    def connect(self, src: str, dst: str) -> Optional[str]
    def disconnect(self, src: str, dst: str) -> Optional[str]
    def wait_ports(self, ports: Sequence[str], timeout_s: float = 15.0) -> List[str]  # returns still-missing
    async def load_carla_project(self, path: str) -> Optional[str]
    async def save_carla_project(self, path: str) -> Optional[str]
    async def import_rig_state(self, state: dict, chains_dir: str) -> dict
    async def export_rig_state(self, chains_dir: str) -> Optional[dict]
    async def load_looper_session(self, project_path: str) -> Optional[str]
    async def looper_save_session_at(self, dir_path: str) -> Optional[str]
    async def looper_get_state(self) -> Optional[dict]
    async def set_looper_mutes(self, main_muted: bool, all_muted: bool) -> Optional[str]

async def do_routing_reset(ops: RigOps) -> str
async def do_verify(graph: RigGraph, ops: RigOps) -> str
```
- Consumes: `in_rig_port_space`, `diff`, `render_report` (Tasks 3–5).

**Steps:**

- [ ] Write failing test `tests/test_rig_converge_reset_verify.py`:

```python
"""Tests for rig/converge.py — routing reset and read-only verify."""

import asyncio

from carla_mcp.rig.converge import RigOps, do_routing_reset, do_verify
from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, ObservedState


class FakeOps(RigOps):
    def __init__(self, links, outputs=(), inputs=(), units_up=()):
        self.links = set(links)
        self.outputs = list(outputs)
        self.inputs = list(inputs)
        self.units_up = set(units_up)
        self.disconnected = []

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph else []
        return ObservedState(
            links=[Link(s, d) for s, d in sorted(self.links)],
            output_ports=self.outputs,
            input_ports=self.inputs,
            unit_status={u.name: u.name in self.units_up for u in units},
        )

    def disconnect(self, src, dst):
        if (src, dst) not in self.links:
            return "no such link"
        self.links.discard((src, dst))
        self.disconnected.append((src, dst))
        return None


MON = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"


class TestRoutingReset:
    def test_clears_only_rig_space(self):
        ops = FakeOps(links={
            ("loopers:loop0_out_l", "Carla:audio-in3"),
            ("CarlaChain_strat:audio-out1", MON),
            ("Firefox:output_FL", MON),
        })
        report = asyncio.run(do_routing_reset(ops))
        assert report.splitlines()[0] == "OK"
        assert ("Firefox:output_FL", MON) in ops.links
        assert len(ops.disconnected) == 2

    def test_failed_disconnect_degrades_verdict(self):
        class StubbornOps(FakeOps):
            def disconnect(self, src, dst):
                return "device busy"
        ops = StubbornOps(links={("loopers:loop0_out_l", "Carla:audio-in3")})
        report = asyncio.run(do_routing_reset(ops))
        assert report.splitlines()[0] == "DEGRADED: 1 issues"
        assert "device busy" in report

    def test_nothing_to_clear_is_ok(self):
        report = asyncio.run(do_routing_reset(FakeOps(links=set())))
        assert report.splitlines()[0] == "OK"


class TestVerify:
    def _graph(self):
        g = RigGraph()
        g.add_node(Node(name="loop:0", kind="loop", port_index=0))
        g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat"))
        g.add_edge("loop:0", "strat")
        g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
        return g

    def test_clean_rig_verifies_ok(self):
        ops = FakeOps(
            links={("loopers:loop0_out_l", "CarlaChain_strat:audio-in1"),
                   ("loopers:loop0_out_r", "CarlaChain_strat:audio-in2")},
            outputs=["loopers:loop0_out_l", "loopers:loop0_out_r",
                     "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2"],
            inputs=["CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
                    "loopers:loop0_in_l", "loopers:loop0_in_r"],
            units_up={"carla:strat"},
        )
        report = asyncio.run(do_verify(self._graph(), ops))
        assert report.splitlines()[0] == "OK"

    def test_broken_rig_names_every_issue(self):
        ops = FakeOps(links=set(), outputs=[], inputs=[], units_up=set())
        report = asyncio.run(do_verify(self._graph(), ops))
        assert report.startswith("DEGRADED:")
        assert "down unit: carla:strat" in report
        assert "absent node:" in report
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_converge_reset_verify.py -v` — expect `ModuleNotFoundError: No module named 'carla_mcp.rig.converge'`.
- [ ] Implement `rig/converge.py`:

```python
"""
Converge engine: drives the rig from observed reality toward the desired
graph through an injectable side-effect interface (RigOps).

The bridge implements RigOps with pw-link / SSE / looper-TCP; tests implement
it with in-memory fakes.  All verdict logic lives here so load / verify /
reset / save / stop cannot drift apart.

stdlib-only: imported by the main Carla process (system Python).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import ObservedState, loop_nodes_from_looper_state
from carla_mcp.rig.reconcile import (
    Action, UNIT_START_ORDER, canonical_ports, diff, expand_edges,
    in_rig_port_space, plan, render_report,
)
from carla_mcp.rig.session import (
    LOOPER_PROJECT, RigSession, SessionError, read_session,
    verify_session_files, write_session,
)

LOAD_PORT_TIMEOUT_S = 15.0


class RigOps:
    """Side-effect interface the converge engine drives.

    Mutating methods return None on success or an error string on failure
    (expected failures never raise).  Data methods return data or None.
    """

    async def observe(self, graph: Optional[RigGraph]) -> ObservedState:
        raise NotImplementedError

    async def start_unit(self, unit: RuntimeUnit) -> Optional[str]:
        raise NotImplementedError

    async def stop_unit(self, unit: RuntimeUnit) -> Optional[str]:
        raise NotImplementedError

    def connect(self, src: str, dst: str) -> Optional[str]:
        raise NotImplementedError

    def disconnect(self, src: str, dst: str) -> Optional[str]:
        raise NotImplementedError

    def wait_ports(self, ports: Sequence[str], timeout_s: float = LOAD_PORT_TIMEOUT_S) -> List[str]:
        raise NotImplementedError

    async def load_carla_project(self, path: str) -> Optional[str]:
        raise NotImplementedError

    async def save_carla_project(self, path: str) -> Optional[str]:
        raise NotImplementedError

    async def import_rig_state(self, state: dict, chains_dir: str) -> dict:
        raise NotImplementedError

    async def export_rig_state(self, chains_dir: str) -> Optional[dict]:
        raise NotImplementedError

    async def load_looper_session(self, project_path: str) -> Optional[str]:
        raise NotImplementedError

    async def looper_save_session_at(self, dir_path: str) -> Optional[str]:
        raise NotImplementedError

    async def looper_get_state(self) -> Optional[dict]:
        raise NotImplementedError

    async def set_looper_mutes(self, main_muted: bool, all_muted: bool) -> Optional[str]:
        raise NotImplementedError


async def do_routing_reset(ops: RigOps) -> str:
    """Clean slate: disconnect every live link in rig port space."""
    observed = await ops.observe(None)
    cleared: List[str] = []
    failures: List[str] = []
    for link in observed.links:
        if not in_rig_port_space(link.src, link.dst):
            continue
        err = ops.disconnect(link.src, link.dst)
        if err:
            failures.append(f"{link.src} -> {link.dst}: {err}")
        else:
            cleared.append(f"{link.src} -> {link.dst}")
    verdict = "OK" if not failures else f"DEGRADED: {len(failures)} issues"
    return render_report(verdict, [("Cleared", cleared), ("Failed", failures)])


async def do_verify(graph: RigGraph, ops: RigOps) -> str:
    """Read-only: observe, diff against the desired graph, report."""
    observed = await ops.observe(graph)
    d = diff(graph, observed)
    return render_report(d.verdict, [("Issues", d.issues())])
```

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_converge_reset_verify.py -v`
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/converge.py source/frontend/carla_mcp/tests/test_rig_converge_reset_verify.py
git commit -m "feat(rig): converge engine skeleton with routing reset and verify

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

