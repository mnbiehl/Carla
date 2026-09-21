"""
Converge engine: drives the rig from observed reality toward the desired
graph through an injectable side-effect interface (RigOps).

The bridge implements RigOps with pw-link / SSE / looper-TCP; tests implement
it with in-memory fakes.  All verdict logic lives here so load / verify /
reset / save / stop cannot drift apart.

stdlib-only: imported by the main Carla process (system Python).
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import List, Optional, Sequence

from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import ObservedState, loop_nodes_from_looper_state
from carla_mcp.rig.reconcile import (
    Action, LOOPER_MIDI_IN, UNIT_START_ORDER, RigDiff, canonical_ports, diff,
    edges_kept_for_absent_hardware, expand_edges, in_rig_port_space, is_rig_port, plan,
    port_device, render_report, stand_in_links,
)
from carla_mcp.rig.session import (
    LOOPER_PROJECT, RigSession, SessionError, read_session,
    verify_session_files, write_session,
)

LOAD_PORT_TIMEOUT_S = 15.0
# a2j enumerates its ports within a moment of starting; a MIDI device that is
# not there by then is unplugged.
A2J_PORT_GRACE_S = 3.0


class RigOps:
    """Side-effect interface the converge engine drives.

    Mutating methods return None on success or an error string on failure
    (expected failures never raise).  Data methods return data or None.

    `connect`, `disconnect` and `wait_ports` may be plain functions (the pure
    test fakes) or coroutine functions (BridgeOps runs pw-link off the event
    loop); the converge engine awaits their result when it is awaitable.
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
        err = await _result(ops.disconnect(link.src, link.dst))
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


async def _result(value):
    """Result of a RigOps link method, whether it returned a value or an awaitable."""
    return await value if inspect.isawaitable(value) else value


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
    elif action.op == "disconnect":
        err = await _result(ops.disconnect(action.src, action.dst))
        if err:
            notes.append(f"disconnect {action.src} -> {action.dst}: {err}")
    elif action.op == "connect":
        err = await _result(ops.connect(action.src, action.dst))
        if err:
            notes.append(f"connect {action.src} -> {action.dst}: {err}")


async def _wait_for_own_ports(ports: Sequence[str], a2j_fresh: bool, ops: RigOps,
                              notes: List[str]) -> None:
    """Wait only for ports this load can make appear: rig clients, and a2j's
    when a2j was started just now. Ports of other hardware are either live
    already or unplugged, so waiting on them only delays the load; the diff
    reports them as a device not found."""
    own = [p for p in ports if is_rig_port(p)]
    if own:
        for port in await _result(ops.wait_ports(own)):
            notes.append(f"port never appeared: {port}")
    a2j = [p for p in ports if p.startswith("a2j:")] if a2j_fresh else []
    if a2j:
        await _result(ops.wait_ports(a2j, timeout_s=A2J_PORT_GRACE_S))


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
            err = await _result(ops.disconnect(link.src, link.dst))
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
    for port in await _result(ops.wait_ports(wanted)):
        notes.append(f"port never appeared: {port}")

    # 5. Connect every desired pair (missing-only; slate is already clean).
    observed = await ops.observe(graph)
    expansion = expand_edges(graph, observed.output_ports, observed.input_ports)
    live = {(l.src, l.dst) for l in observed.links}
    for pair in expansion.pairs:
        if (pair.src, pair.dst) in live:
            continue
        err = await _result(ops.connect(pair.src, pair.dst))
        if err:
            notes.append(f"connect {pair.src} -> {pair.dst}: {err}")

    # 6. Verify; one retry round through plan() if not clean.
    observed = await ops.observe(graph)
    d = diff(graph, observed)
    if not d.is_clean:
        a2j_fresh = any(graph.runtime_units[name].kind == "a2j"
                        for name in [u.name for u in down] + d.down_units)
        for action in plan(d, graph):
            if action.op == "wait_ports":
                await _wait_for_own_ports(action.ports, a2j_fresh, ops, notes)
            else:
                await _apply_action(action, graph, ops, notes)
        observed = await ops.observe(graph)
        d = diff(graph, observed)

    return render_report(d.verdict, [("Issues", d.issues()), ("Notes", notes)])


# The plan() steps a rewire may take. start_unit and wait_ports are dropped:
# a rewire never changes processes and never blocks waiting for ports.
REWIRE_OPS = ("disconnect", "connect")

PORT_LISTING_UNAVAILABLE_NOTE = (
    "port listing unavailable (pw-link -o/-i returned nothing); refusing to disconnect"
)


def _safe_disconnects(planned: List[Action], output_ports: set, input_ports: set) -> List[Action]:
    """Drop any planned disconnect whose endpoints are not both confirmed live.

    A disconnect is only trustworthy when its src is a known-live output port
    and its dst is a known-live input port. If `pw-link -o`/`-i` fail or time
    out (utils/pw_link.py returns [] on either), every live rig-space link
    would otherwise look "unexpected" and this would tear down a healthy rig
    mid-performance — even though `pw-link -l` (a separate subprocess) still
    reported real links. Connects are unaffected: they are only ever planned
    for port pairs already confirmed live by expand_edges.
    """
    return [a for a in planned
           if a.op != "disconnect" or (a.src in output_ports and a.dst in input_ports)]


def _link_text(action: Action) -> str:
    return f"{action.src} -> {action.dst}"


@dataclass
class Rewire:
    """Outcome of do_rewire.

    `planned` is the disconnect/connect subset of plan() for the first
    observation, disconnects first. `applied` holds the actions that succeeded
    and `failures` the ones that did not; both stay empty on a dry run.
    `diff` is the post-rewire diff, or the pre-rewire one on a dry run.
    """

    planned: List[Action]
    diff: RigDiff
    applied: List[Action] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    @property
    def unfixable(self) -> List[str]:
        """Issues no link change can fix: down units, absent nodes, dead ports,
        unresolved effects."""
        return replace(self.diff, missing_edges=[], unexpected_connections=[]).issues()

    def report(self) -> str:
        return render_report(self.diff.verdict, [
            ("Disconnected", [_link_text(a) for a in self.applied if a.op == "disconnect"]),
            ("Connected", [_link_text(a) for a in self.applied if a.op == "connect"]),
            ("Issues", self.diff.issues()),
            ("Failures", self.failures),
        ])


async def do_rewire(graph: RigGraph, ops: RigOps, dry_run: bool = False) -> Rewire:
    """Put rig routing back to *graph* by changing links only.

    Disconnects live rig-space links the graph does not want and connects its
    missing port pairs, using the same diff() -> plan() -> _apply_action path
    as do_load's verify-and-retry step. Never starts or stops units, never
    waits for ports, never loads Carla or looper payload. With *dry_run* the
    plan is returned and nothing is applied.

    Never disconnects a link unless both its endpoints are in the observed
    output/input port lists; if those lists come back empty while links are
    still reported, every disconnect is refused and the report notes why
    (see PORT_LISTING_UNAVAILABLE_NOTE).
    """
    observed = await ops.observe(graph)
    d = diff(graph, observed)
    planned = [a for a in plan(d, graph) if a.op in REWIRE_OPS]

    output_ports = set(observed.output_ports)
    input_ports = set(observed.input_ports)
    refusal: List[str] = []
    if observed.links and (not output_ports or not input_ports):
        # pw-link -l returned links but -o/-i did not: an inconsistent
        # snapshot, not a rig with nothing stray. Refuse every disconnect
        # rather than treating every live link as unexpected.
        refusal.append(PORT_LISTING_UNAVAILABLE_NOTE)
    planned = _safe_disconnects(planned, output_ports, input_ports)

    if dry_run:
        return Rewire(planned=planned, diff=d, failures=list(refusal))
    applied: List[Action] = []
    failures: List[str] = list(refusal)
    for action in planned:
        errors: List[str] = []
        await _apply_action(action, graph, ops, errors)
        if errors:
            failures.extend(errors)
        else:
            applied.append(action)
    after = diff(graph, await ops.observe(graph))
    return Rewire(planned=planned, diff=after, applied=applied, failures=failures)


_LOOP_PORT_RE = re.compile(r"^loopers:loop(\d+)_(in|out)_(l|r)$")


def _graph_from_export(export: dict, graph: RigGraph, session_dir: Path,
                       notes: List[str]) -> None:
    """Lift a live export_rig_state dict into *graph* (v3 shapes).

    Delegates to the migrator's rig_state lifter so live saves and legacy
    migration can never disagree about node/edge lifting.
    """
    from carla_mcp.rig.session import _lift_rig_state
    _lift_rig_state(export, graph, session_dir, notes)
    for err in export.get("errors", []):
        notes.append(f"carla export: {err}")


def _lift_link(graph: RigGraph, src: str, dst: str, notes: List[str]) -> None:
    """Record one uncovered live rig-space link as an explicit-port edge."""
    from carla_mcp.rig.observe import is_midi_port

    def _node_for(port: str) -> str:
        m = _LOOP_PORT_RE.match(port)
        if m:
            name = f"loop:{m.group(1)}"
            if not graph.has_node(name):
                graph.add_node(Node(name=name, kind="loop",
                                    port_index=int(m.group(1))))
            return name
        if port == LOOPER_MIDI_IN:
            if not graph.has_node("app:looper"):
                graph.add_node(Node(name="app:looper", kind="app"))
            return "app:looper"
        client = port.split(":", 1)[0]
        for node in graph.nodes.values():
            if node.kind in ("track", "bus") and node.jack_client == client:
                return node.name
        if port.startswith("a2j:"):
            name = "midi:pacer" if "acer" in port else f"midi:{client}"
            if not graph.has_node(name):
                graph.add_node(Node(name=name, kind="midi",
                                    port_pattern=re.escape(port)))
            graph.add_runtime_unit(RuntimeUnit(name="a2j", kind="a2j"))
            return name
        if not graph.has_node(port):
            graph.add_node(Node(name=port, kind="endpoint", jack_client=port))
        return port

    kind = "midi" if (is_midi_port(src) or is_midi_port(dst)) else "audio"
    src_node = _node_for(src)
    dst_node = _node_for(dst)
    graph.add_edge(src_node, dst_node, kind=kind, src_port=src, dst_port=dst)


def _keep_absent_hardware(graph: RigGraph, desired: RigGraph, observed: ObservedState,
                          warnings: List[str]) -> set:
    """Carry *desired*'s edges to unplugged hardware into *graph*, and return the
    live links standing in for that hardware, which must not be lifted.

    A session keeps its interface and controller while they are disconnected,
    like a DAW project keeps its audio device; saving without them attached
    must not lose their routing or adopt the onboard-audio fallback.
    """
    kept_per_device: dict = {}
    live = set(observed.output_ports) | set(observed.input_ports)
    for edge in edges_kept_for_absent_hardware(desired, observed.output_ports,
                                               observed.input_ports):
        ends = [desired.get_node(edge.src), desired.get_node(edge.dst)]
        if any(n.kind not in ("endpoint", "midi") and not graph.has_node(n.name) for n in ends):
            continue  # its loop or chain no longer exists
        for node in ends:
            if not graph.has_node(node.name):
                graph.add_node(replace(node))
        graph.add_edge(edge.src, edge.dst, gain_db=edge.gain_db, kind=edge.kind,
                       src_port=edge.src_port, dst_port=edge.dst_port)
        if edge.kind == "midi" and "a2j" in desired.runtime_units:
            graph.add_runtime_unit(replace(desired.runtime_units["a2j"]))
        if edge.src_port and edge.dst_port:
            devices = {port_device(p) for p in (edge.src_port, edge.dst_port) if p not in live}
        else:
            devices = {n.jack_client or n.name for n in ends
                       if n.kind in ("endpoint", "midi") and not is_rig_port(n.jack_client or n.name)}
        for device in devices:
            kept_per_device[device] = kept_per_device.get(device, 0) + 1
    for device, count in kept_per_device.items():
        warnings.append(f"device not found: {device}; kept its {count} session edges")

    stand_ins = stand_in_links(desired, [l for l in observed.links
                                         if in_rig_port_space(l.src, l.dst)],
                               observed.output_ports, observed.input_ports)
    for link in stand_ins:
        warnings.append(f"not saved: {link.src} -> {link.dst} "
                        "(stands in for a device that is not connected)")
    return {(l.src, l.dst) for l in stand_ins}


async def do_save(name: str, session_dir: Path, ops: RigOps,
                  desired: Optional[RigGraph] = None) -> str:
    """Capture the live rig as a v3 session and verify the written output.

    *desired* is the session graph the rig was loaded from, if any. Its edges
    to hardware that is not connected right now are kept (see
    _keep_absent_hardware) and reported under Warnings; they do not degrade
    the verdict.
    """
    notes: List[str] = []
    warnings: List[str] = []
    session_dir.mkdir(parents=True, exist_ok=True)
    graph = RigGraph()
    carla_project: Optional[str] = None
    looper_dir: Optional[str] = None

    export = await ops.export_rig_state(str(session_dir / "chains"))
    if export is not None and "nodes" in export:
        _graph_from_export(export, graph, session_dir, notes)
        err = await ops.save_carla_project(str(session_dir / "carla_project.carxp"))
        if err is None:
            carla_project = "carla_project.carxp"
        else:
            notes.append(f"carla project save: {err}")
        graph.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    elif export is not None:
        # Carla was reachable but the export call itself failed (timeout,
        # tool error): report the real reason, not "carla not reachable".
        notes.append(str(export.get("error", "carla export failed; no Carla state saved")))
    else:
        notes.append("carla not reachable; no Carla state saved")

    state = await ops.looper_get_state()
    if state is not None:
        raw_loopers = (state or {}).get("loopers", []) or []
        loop_nodes = loop_nodes_from_looper_state(state)
        if len(loop_nodes) < len(raw_loopers):
            for entry in raw_loopers:
                if entry.get("port_index") is None:
                    notes.append(
                        f"looper id={entry.get('id')} has no port_index "
                        "(pre-contract engine?); dropped from saved session"
                    )
        for loop_node in loop_nodes:
            if graph.has_node(loop_node.name):
                existing = graph.nodes[loop_node.name]
                existing.looper_id = loop_node.looper_id
                existing.port_index = loop_node.port_index
            else:
                graph.add_node(loop_node)
        if not graph.has_node("app:looper"):
            graph.add_node(Node(name="app:looper", kind="app"))
        app = graph.nodes["app:looper"]
        app.main_muted = bool(state.get("main_muted", False))
        app.all_muted = bool(state.get("all_muted", False))
        graph.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
        graph.add_runtime_unit(RuntimeUnit(name="looper:mcp", kind="looper-mcp"))
        err = await ops.looper_save_session_at(str(session_dir / "looper"))
        if err is None:
            looper_dir = "looper"
        else:
            notes.append(f"looper session save: {err}")
    else:
        notes.append("looper not reachable; no looper state saved")

    if carla_project is None and looper_dir is None:
        return "FAILED: nothing to save (carla and looper both unreachable)"

    # Lift every live rig-space link not covered by graph edges.
    observed = await ops.observe(graph)
    expansion = expand_edges(graph, observed.output_ports, observed.input_ports)
    covered = {(p.src, p.dst) for p in expansion.pairs}
    if desired is not None:
        covered |= _keep_absent_hardware(graph, desired, observed, warnings)
    for link in observed.links:
        if (link.src, link.dst) in covered:
            continue
        if not in_rig_port_space(link.src, link.dst):
            continue
        _lift_link(graph, link.src, link.dst, notes)

    sess = RigSession(name=name, graph=graph, carla_project=carla_project,
                      looper_session_dir=looper_dir)
    write_session(sess, session_dir)

    # Self-verify: the file we just wrote must read back and reference only
    # files that actually exist.
    try:
        reread = read_session(session_dir)
    except SessionError as exc:
        return render_report(f"FAILED: saved session does not re-read: {exc}",
                             [("Notes", notes), ("Warnings", warnings)])
    problems = verify_session_files(reread, session_dir)
    issues = problems + notes
    verdict = "OK" if not issues else f"DEGRADED: {len(issues)} issues"
    return render_report(verdict, [("Problems", problems), ("Notes", notes),
                                   ("Warnings", warnings)])


# Stop order = reverse of UNIT_START_ORDER: carla-child -> carla-main ->
# looper-mcp -> looper-engine -> a2j.  Kept as its own mapping (rather than
# negating UNIT_START_ORDER) because a2j's start rank sits between
# looper-mcp/looper-engine and carla-main, so a naive negation would stop
# a2j too early instead of last.
UNIT_STOP_ORDER = {
    "carla-child": 0,
    "carla-main": 1,
    "looper-mcp": 2,
    "looper-engine": 3,
    "a2j": 4,
}

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
    for unit in sorted(units, key=lambda u: (UNIT_STOP_ORDER.get(u.kind, 9), u.name)):
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
