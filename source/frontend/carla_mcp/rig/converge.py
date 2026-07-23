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
