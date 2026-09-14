"""rig_up / rig_down / rig_state / rig_reset_routing."""

from __future__ import annotations

from typing import List, Optional

from carla_mcp.backends.rpc import RpcError
from carla_mcp.bridge import units
from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.ops import BridgeOps
from carla_mcp.bridge.result import ToolError, ok, tool_boundary
from carla_mcp.bridge.tools import ToolSpec
from carla_mcp.rig.converge import do_routing_reset, do_stop
from carla_mcp.rig.graph import RigGraph
from carla_mcp.rig.reconcile import in_rig_port_space
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


def build(b: Bridge) -> List[ToolSpec]:

    @tool_boundary
    async def rig_up(session: Optional[str] = None) -> dict:
        """Start the rig's processes (a2jmidid, Carla, loopers). With `session`,
        also load that saved rig session (clean-slate, converge, verify)."""
        started: List[str] = []
        notes: List[str] = []
        for name, starter in (("a2j", units.start_a2j), ("carla:main", units.start_carla_main),
                              ("looper:engine", units.start_looper_engine)):
            result = starter(b)
            err = await result if hasattr(result, "__await__") else result
            if err is None:
                started.append(name)
            else:
                notes.append(err)
        if session is not None:
            from carla_mcp.bridge.tools.sessions import load_session_into
            notes.extend(await load_session_into(b, session))
        state = await _state(b, b.graph, b.session_name, None, "normal")
        return ok({"started": started, "state": state}, notes=notes)

    @tool_boundary
    async def rig_down() -> dict:
        """Stop every rig process in reverse start order. Unsaved loop audio is lost."""
        report = await do_stop(b.graph, BridgeOps(b))
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
            try:
                graph = read_session(b.config.session_dir / compare).graph
            except SessionError as exc:
                raise ToolError("not_found", f"session {compare!r}: {exc}") from exc
            session = compare
        return ok(await _state(b, graph, session, focus, detail))

    @tool_boundary
    async def rig_reset_routing(dry_run: bool = False) -> dict:
        """Disconnect every live link in rig port space (loopers/Carla). Use when
        PipeWire restored stale links. `dry_run` lists what would be cut."""
        if dry_run:
            observed = await BridgeOps(b).observe(None)
            links = [{"src": l.src, "dst": l.dst} for l in observed.links
                     if in_rig_port_space(l.src, l.dst)]
            return ok({"dry_run": True, "would_disconnect": links})
        return ok({"dry_run": False, "report": await do_routing_reset(BridgeOps(b))})

    return [
        ToolSpec("rig_up", rig_up, {"idempotentHint": True}),
        ToolSpec("rig_down", rig_down, {"destructiveHint": True}),
        ToolSpec("rig_state", rig_state, {"readOnlyHint": True}),
        ToolSpec("rig_reset_routing", rig_reset_routing, {"destructiveHint": True}),
    ]
