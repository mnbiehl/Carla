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


def rig_state_for_import(graph: RigGraph, session_dir: Path) -> dict:
    """Build an import_rig_state payload from the session graph.

    Edges are deliberately empty: the converge engine owns ALL wiring (the
    controller must not race it).  Track sources that name loop:N nodes are
    translated to the "loopers:loopN_out" endpoint base the controller can
    resolve; chain_file paths are absolutized against the session dir.
    """
    nodes: List[dict] = []
    endpoint_bases: List[str] = []

    def _translate_source(source: Optional[str]) -> Optional[str]:
        if source and graph.has_node(source):
            src_node = graph.nodes[source]
            if src_node.kind == "loop":
                base = f"loopers:loop{src_node.port_index}_out"
                if base not in endpoint_bases:
                    endpoint_bases.append(base)
                return base
        return source

    for node in graph.nodes.values():
        if node.kind not in ("endpoint", "track", "bus"):
            continue
        chain_file = node.chain_file
        if chain_file and not Path(chain_file).is_absolute():
            chain_file = str(session_dir / chain_file)
        nodes.append({
            "name": node.name,
            "kind": node.kind,
            "instance": node.instance,
            "jack_client": node.jack_client,
            "source": _translate_source(node.source),
            "effects": [
                {"role": e.role, "handle": e.handle, "plugin": e.plugin,
                 "bypassed": e.bypassed}
                for e in node.effects
            ],
            "chain_file": chain_file,
        })
    for base in endpoint_bases:
        if not any(n["name"] == base for n in nodes):
            nodes.append({"name": base, "kind": "endpoint", "instance": None,
                          "jack_client": base, "source": None, "effects": [],
                          "chain_file": None})
    return {"version": 1, "nodes": nodes, "edges": []}


async def _apply_action(action: Action, graph: RigGraph, ops: RigOps,
                        notes: List[str]) -> None:
    """Execute one plan action, recording every failure in *notes*."""
    if action.op == "start_unit":
        unit = graph.runtime_units.get(action.unit)
        if unit is None:
            notes.append(f"start {action.unit}: unknown runtime unit")
            return
        err = await ops.start_unit(unit)
        if err:
            notes.append(f"start {unit.name}: {err}")
    elif action.op == "wait_ports":
        for port in ops.wait_ports(list(action.ports)):
            notes.append(f"port never appeared: {port}")
    elif action.op == "disconnect":
        err = ops.disconnect(action.src, action.dst)
        if err:
            notes.append(f"disconnect {action.src} -> {action.dst}: {err}")
    elif action.op == "connect":
        err = ops.connect(action.src, action.dst)
        if err:
            notes.append(f"connect {action.src} -> {action.dst}: {err}")


async def do_load(name: str, session_dir: Path, ops: RigOps) -> str:
    """Load a session: read/migrate -> clean slate -> converge -> verify."""
    try:
        sess = read_session(session_dir)
    except SessionError as exc:
        return f"FAILED: {exc}"
    graph = sess.graph
    notes: List[str] = list(sess.notes)

    # 1. Processes: start every expected unit that is down, in start order.
    observed = await ops.observe(graph)
    down = [u for u in graph.runtime_units.values()
            if not observed.unit_status.get(u.name, False)]
    for unit in sorted(down, key=lambda u: (UNIT_START_ORDER.get(u.kind, 9), u.name)):
        err = await ops.start_unit(unit)
        if err:
            notes.append(f"start {unit.name}: {err}")

    # 2. Clean slate: beat PipeWire persistent-link restoration.
    observed = await ops.observe(graph)
    for link in observed.links:
        if in_rig_port_space(link.src, link.dst):
            err = ops.disconnect(link.src, link.dst)
            if err:
                notes.append(f"clean-slate {link.src} -> {link.dst}: {err}")

    # 3. Payload: projects, per-track chains, looper session, mutes.
    if sess.carla_project:
        err = await ops.load_carla_project(str(session_dir / sess.carla_project))
        if err:
            notes.append(f"carla project: {err}")
    state = rig_state_for_import(graph, session_dir)
    if any(n["kind"] in ("track", "bus") for n in state["nodes"]):
        result = await ops.import_rig_state(state, str(session_dir / "chains"))
        for message in result.get("messages", []):
            notes.append(f"rig import: {message}")
    if sess.looper_session_dir:
        project = session_dir / sess.looper_session_dir / LOOPER_PROJECT
        err = await ops.load_looper_session(str(project))
        if err:
            notes.append(f"looper session: {err}")
        app = graph.nodes.get("app:looper")
        if app is not None:
            err = await ops.set_looper_mutes(app.main_muted, app.all_muted)
            if err:
                notes.append(f"looper mutes: {err}")

    # 4. Wait for every canonically-named port before wiring.
    wanted = sorted({p for n in graph.nodes.values() for p in canonical_ports(n)})
    for port in ops.wait_ports(wanted):
        notes.append(f"port never appeared: {port}")

    # 5. Connect every desired pair (missing-only; slate is already clean).
    observed = await ops.observe(graph)
    expansion = expand_edges(graph, observed.output_ports, observed.input_ports)
    for message in expansion.dead_ports:
        notes.append(message)
    live = {(l.src, l.dst) for l in observed.links}
    for pair in expansion.pairs:
        if (pair.src, pair.dst) in live:
            continue
        err = ops.connect(pair.src, pair.dst)
        if err:
            notes.append(f"connect {pair.src} -> {pair.dst}: {err}")

    # 6. Verify; one retry round through plan() if not clean.
    observed = await ops.observe(graph)
    d = diff(graph, observed)
    if not d.is_clean:
        for action in plan(d, graph):
            await _apply_action(action, graph, ops, notes)
        observed = await ops.observe(graph)
        d = diff(graph, observed)

    return render_report(d.verdict, [("Issues", d.issues()), ("Notes", notes)])
