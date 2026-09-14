"""session_save / session_load / session_list."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.ops import BridgeOps
from carla_mcp.bridge.result import ToolError, ok, tool_boundary
from carla_mcp.bridge.tools import ToolSpec
from carla_mcp.rig.converge import do_load, do_save
from carla_mcp.rig.session import SessionError, read_session

POLL_S = 0.5
LOOPER_SAVE_TIMEOUT_S = 10.0
_SESSION_FILES = ("rig_session.json", "rig_manifest.json")


def _session_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and any((p / f).exists() for f in _SESSION_FILES))


async def load_session_into(b: Bridge, name: str) -> List[str]:
    """do_load into the bridge; returns notes. Sets b.graph / b.session_name."""
    sdir = b.config.session_dir / name
    if not sdir.is_dir():
        raise ToolError("not_found", f"no rig session named {name!r} in {b.config.session_dir}")
    report = await do_load(name, sdir, BridgeOps(b))
    try:
        b.graph = read_session(sdir).graph
        b.session_name = name
    except SessionError as exc:
        raise ToolError("degraded", f"loaded but could not re-read session: {exc}") from exc
    return [report]


async def _wait_for_looper_project(sdir: Path) -> Optional[str]:
    target = sdir / "looper" / "project.loopers"
    waited = 0.0
    while waited < LOOPER_SAVE_TIMEOUT_S:
        if target.exists():
            return None
        await asyncio.sleep(POLL_S)
        waited += POLL_S
    return f"looper project not written within {LOOPER_SAVE_TIMEOUT_S:.0f}s: {target}"


def build(b: Bridge) -> List[ToolSpec]:

    @tool_boundary
    async def session_save(name: str, overwrite: bool = False) -> dict:
        """Save the live rig (Carla state, chains, looper session with loop audio, routing)
        as a named rig session. The only durable state — loop audio is memory-only until saved."""
        sdir = b.config.session_dir / name
        if sdir.exists() and not overwrite:
            raise ToolError("validation", f"session {name!r} exists; pass overwrite=True")
        report = await do_save(name, sdir, BridgeOps(b))
        notes: List[str] = []
        race = await _wait_for_looper_project(sdir)
        if race:
            notes.append(race)
        try:
            b.graph = read_session(sdir).graph
            b.session_name = name
        except SessionError as exc:
            notes.append(f"saved but could not re-read session: {exc}")
        return ok({"report": report, "path": str(sdir)}, notes=notes)

    @tool_boundary
    async def session_load(name: str) -> dict:
        """Load a saved rig session: start missing units, clean-slate rig routing,
        converge to the saved graph, verify. Replaces the loops currently in memory."""
        from carla_mcp.bridge.tools.lifecycle import _state
        notes = await load_session_into(b, name)
        state = await _state(b, b.graph, b.session_name, None, "normal")
        return ok({"report": notes[0], "state": state})

    @tool_boundary
    async def session_list() -> dict:
        """Names of saved rig sessions."""
        return ok([p.name for p in _session_dirs(b.config.session_dir)])

    return [
        ToolSpec("session_save", session_save, {}),
        ToolSpec("session_load", session_load, {"destructiveHint": True}),
        ToolSpec("session_list", session_list, {"readOnlyHint": True}),
    ]
