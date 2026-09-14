"""rig_up / rig_down / rig_state / rig_reset_routing."""

from __future__ import annotations

from typing import List, Optional

from carla_mcp.backends.processes import tcp_reachable
from carla_mcp.backends.rpc import RpcError
from carla_mcp.bridge import units
from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.ops import BridgeOps
from carla_mcp.bridge.result import ToolError, ok, tool_boundary
from carla_mcp.bridge.tools import ToolSpec, exclusive
from carla_mcp.rig.converge import Action, do_rewire, do_stop
from carla_mcp.rig.graph import RigGraph, RuntimeUnit
from carla_mcp.rig.reconcile import UNIT_START_ORDER
from carla_mcp.rig.session import SessionError, read_session
from carla_mcp.rig.state_view import DETAILS, build_state


async def _loopers(b: Bridge) -> list:
    try:
        return await b.looper.loopers()
    except RpcError:
        return []


async def _versions(b: Bridge) -> dict:
    try:
        carla = (await b.carla.version()).get("worker", "unknown")
    except RpcError:
        carla = "down"
    return {"bridge": b.version, "carla": carla}


async def _state(b: Bridge, graph: Optional[RigGraph], session: Optional[str],
                 focus: Optional[str], detail: str) -> dict:
    observed = await BridgeOps(b).observe(graph)
    return build_state(graph, observed, await _loopers(b), await _versions(b), session,
                       focus=focus, detail=detail)


# Units whose presence means a performance may be live (loops in memory,
# routing in place). rig_up only loads a session onto a cold rig.
SESSION_GUARD_UNITS = (("carla:main", "carla-main"), ("looper:engine", "looper-engine"))

RIG_ALREADY_UP_MESSAGE = "rig is already up; use session_load (destructive) to replace the running session"


def _session_guard_units_up(b: Bridge) -> List[str]:
    ops = BridgeOps(b)
    up: List[str] = []
    for name, kind in SESSION_GUARD_UNITS:
        if ops.unit_probe(RuntimeUnit(name=name, kind=kind)):
            up.append(name)
        elif kind == "carla-main" and units.carla_running_without_worker(b):
            # RPC is closed, but a Carla without the worker still holds rig-space
            # links a session load would clear (start_carla_main refuses on this too).
            up.append(f"{name} (running without the RPC worker)")
        elif kind == "looper-engine" and tcp_reachable("127.0.0.1", b.config.looper_port):
            # The looper-engine probe above is pw-link-based (ports_present); if
            # pw-link fails or times out it reads as down even with loops still
            # in memory. The looper's own TCP port is an independent check.
            up.append(f"{name} (TCP port reachable; pw-link ports not seen)")
    return up


NO_SESSION_TO_RESET_MESSAGE = "no session loaded; nothing to reset routing to (use session_load)"


def _loaded_graph(b: Bridge) -> RigGraph:
    if b.graph is None:
        raise ToolError("validation", NO_SESSION_TO_RESET_MESSAGE)
    return b.graph


def _links(actions: List[Action], op: str) -> List[dict]:
    return [{"src": a.src, "dst": a.dst} for a in actions if a.op == op]


def build(b: Bridge) -> List[ToolSpec]:
    # Map unit kinds to (unit name, starter function). Starters are None for legacy/session units.
    _unit_starters = {
        "looper-engine": ("looper:engine", units.start_looper_engine),
        "a2j": ("a2j", units.start_a2j),
        "carla-main": ("carla:main", units.start_carla_main),
    }

    @tool_boundary
    async def rig_up(session: Optional[str] = None) -> dict:
        """Start the rig's processes in order (looper-engine, a2j, carla-main); safe to repeat.
        With `session`, also load that saved rig session (clean-slate, converge, verify),
        but only on a cold start: if Carla or the looper is already up it refuses, because
        loading replaces the loops in memory. Use session_load for that."""
        async with exclusive(b):
            if session is not None:
                already_up = _session_guard_units_up(b)
                if already_up:
                    raise ToolError("validation", RIG_ALREADY_UP_MESSAGE,
                                    notes=[f"up: {', '.join(already_up)}"])
            started: List[str] = []
            notes: List[str] = []
            # Start units in UNIT_START_ORDER, skipping those without a starter (legacy looper-mcp, session carla-child).
            for kind in sorted(_unit_starters.keys(), key=lambda k: UNIT_START_ORDER.get(k, 9)):
                name, starter = _unit_starters[kind]
                result = starter(b)
                err = await result if hasattr(result, "__await__") else result
                if err is None:
                    started.append(name)
                else:
                    notes.append(err)
            if session is not None:
                from carla_mcp.bridge.tools.sessions import load_session_into
                try:
                    notes.extend(await load_session_into(b, session))
                except ToolError as exc:
                    # Units are already up even though the load FAILed: tell
                    # the caller what it now needs to tear down, rather than
                    # dropping that context at the tool boundary.
                    context: List[str] = []
                    if started:
                        context.append(f"started: {', '.join(started)}")
                    context.extend(notes)
                    context.extend(exc.notes)
                    raise ToolError(exc.type, exc.message, notes=context) from exc
            state = await _state(b, b.graph, b.session_name, None, "normal")
            return ok({"started": started, "state": state}, notes=notes)

    @tool_boundary
    async def rig_down() -> dict:
        """Stop every rig process in reverse start order. Unsaved loop audio is lost.
        Units this bridge did not start (e.g. after a bridge restart) are left running
        and reported as issues."""
        async with exclusive(b):
            report = await do_stop(b.graph, BridgeOps(b))
            # Forget the desired graph only when the rig is really down; a
            # DEGRADED stop leaves units running that the graph still describes.
            if report.startswith("OK"):
                b.graph = None
                b.session_name = None
            return ok({"report": report})

    @tool_boundary
    async def rig_state(focus: Optional[str] = None, detail: str = "normal",
                        compare: Optional[str] = None) -> dict:
        """The one truth call: verdict first, then units, loops table and rig-space links.
        `focus` narrows to a node or `loop:N`; `detail` is normal|diagram|io;
        `compare=<session>` verifies the live rig against that saved session."""
        if detail not in DETAILS:
            raise ToolError("validation", f"detail must be one of {DETAILS}")
        graph, session = b.graph, b.session_name
        if compare is not None:
            from carla_mcp.bridge.tools.sessions import session_path
            sdir = session_path(b, compare)
            try:
                graph = read_session(sdir).graph
            except SessionError as exc:
                raise ToolError("not_found", f"session {compare!r}: {exc}") from exc
            session = compare
        return ok(await _state(b, graph, session, focus, detail))

    @tool_boundary
    async def rig_reset_routing(dry_run: bool = False) -> dict:
        """Rewire the rig to the loaded session's routing. Disconnects every rig-space link
        (loopers/Carla) the session does not want, then connects the session's missing
        edges. Hand-wiring made since the last session_load or session_save counts as
        stray and will be removed. Only links change: no process is started or stopped,
        Carla and the looper are not reloaded, and loops in memory are untouched. Refuses
        when no session is loaded. Down units, absent nodes and dead ports cannot be fixed
        by rewiring and are reported. Run with `dry_run=True` first to see the planned
        disconnects and connects before applying them."""
        if dry_run:
            rewire = await do_rewire(_loaded_graph(b), BridgeOps(b), dry_run=True)
            return ok({"dry_run": True,
                       "would_disconnect": _links(rewire.planned, "disconnect"),
                       "would_connect": _links(rewire.planned, "connect"),
                       "not_fixable_by_rewiring": rewire.unfixable})
        async with exclusive(b):
            rewire = await do_rewire(_loaded_graph(b), BridgeOps(b))
            return ok({"dry_run": False,
                       "verdict": rewire.diff.verdict,
                       "disconnected": _links(rewire.applied, "disconnect"),
                       "connected": _links(rewire.applied, "connect"),
                       "report": rewire.report()}, notes=rewire.failures)

    return [
        ToolSpec("rig_up", rig_up, {"idempotentHint": True}),
        ToolSpec("rig_down", rig_down, {"destructiveHint": True}),
        ToolSpec("rig_state", rig_state, {"readOnlyHint": True}),
        ToolSpec("rig_reset_routing", rig_reset_routing, {"destructiveHint": True}),
    ]
