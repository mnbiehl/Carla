"""session_save / session_load / session_list."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.ops import BridgeOps
from carla_mcp.bridge.result import ToolError, ok, tool_boundary
from carla_mcp.bridge.tools import ToolSpec, exclusive
from carla_mcp.rig.converge import do_load, do_save
from carla_mcp.rig.graph import RigGraph
from carla_mcp.rig.session import SessionError, read_session

_SESSION_FILES = ("rig_session.json", "rig_manifest.json")


def _session_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and any((p / f).exists() for f in _SESSION_FILES))


def session_path(b: Bridge, name: str) -> Path:
    """Resolve a session `name` to a directory directly under `session_dir`.

    Raises ToolError("validation", ...) for anything that isn't a plain,
    single-segment directory name — in particular anything that could make
    `session_dir / name` escape session_dir (absolute paths, `..`, path
    separators, hidden-file-style leading dots).
    """
    session_dir = b.config.session_dir
    reason = None
    if not isinstance(name, str) or not name:
        reason = "must be a non-empty string"
    elif Path(name).is_absolute():
        reason = "must not be an absolute path"
    elif "/" in name or "\\" in name:
        reason = "must be a single path segment, with no '/' or '\\'"
    elif name in (".", "..") or ".." in Path(name).parts:
        reason = "must not be '.' or '..'"
    elif name.startswith("."):
        reason = "must not start with '.'"
    if reason is not None:
        raise ToolError("validation",
                         f"invalid session name {name!r}: {reason} "
                         "(use a plain name like 'tues-jam')")
    sdir = session_dir / name
    if sdir.resolve().parent != session_dir.resolve():
        raise ToolError("validation", f"session name {name!r} escapes the session directory")
    return sdir


def _failed_save_notes(report: str, sdir: Path, created_dir: bool) -> List[str]:
    """Notes for a FAILED save. If this call created `sdir` and it is still empty,
    remove it so it does not block a re-save. Only a plain rmdir of an empty
    directory this call created — never recursive, never a pre-existing one."""
    notes: List[str] = [report] if "\n" in report.strip() else []
    if created_dir and sdir.is_dir() and not any(sdir.iterdir()):
        try:
            sdir.rmdir()
        except OSError as exc:
            notes.append(f"could not remove empty session directory {sdir}: {exc}")
    return notes


def _desired_for_save(b: Bridge, sdir: Path) -> Optional[RigGraph]:
    """The graph whose routing to unplugged hardware a save must keep: the loaded
    session, else (e.g. after a bridge restart) the session being overwritten."""
    if b.graph is not None:
        return b.graph
    try:
        return read_session(sdir).graph
    except (SessionError, KeyError, TypeError, ValueError):  # unreadable or malformed: the overwrite replaces it anyway
        return None


async def load_session_into(b: Bridge, name: str) -> List[str]:
    """do_load into the bridge; returns notes. Sets b.graph / b.session_name, except
    on a FAILED load, which raises `degraded` and leaves both unchanged."""
    sdir = session_path(b, name)
    if not sdir.is_dir():
        raise ToolError("not_found", f"no rig session named {name!r} in {b.config.session_dir}")
    report = await do_load(name, sdir, BridgeOps(b))
    if report.startswith("FAILED"):
        raise ToolError("degraded", report.splitlines()[0],
                        notes=[report] if "\n" in report.strip() else [])
    try:
        b.graph = read_session(sdir).graph
        b.session_name = name
    except SessionError as exc:
        raise ToolError("degraded", f"loaded but could not re-read session: {exc}") from exc
    return [report]


def build(b: Bridge) -> List[ToolSpec]:

    @tool_boundary
    async def session_save(name: str, overwrite: bool = False) -> dict:
        """Save the live rig (Carla state, chains, looper session with loop audio, routing)
        as a named rig session. The only durable state — loop audio is memory-only until saved.
        Routing to a session device that is not connected right now (audio interface, MIDI
        controller) is kept, not dropped, and listed under Warnings in the report."""
        sdir = session_path(b, name)
        async with exclusive(b):
            if sdir.is_dir() and not overwrite:
                raise ToolError("validation", f"session {name!r} exists; pass overwrite=True")
            created_dir = not sdir.exists()
            report = await do_save(name, sdir, BridgeOps(b), desired=_desired_for_save(b, sdir))
            if report.startswith("FAILED"):
                raise ToolError("degraded", report.splitlines()[0],
                                notes=_failed_save_notes(report, sdir, created_dir))
            notes: List[str] = []
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
        async with exclusive(b):
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
