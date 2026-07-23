"""
Rig session manifest v3: one JSON file (rig_session.json) holding the whole
desired state — nodes (with per-track .carxp pointers), edges, looper session
path, runtime-unit expectations.

Read-time migration converts legacy v1/v2 sessions (rig_manifest.json +
rig_state.json + looper project) to a v3 RigSession.  There is no write
support for old formats: the first save after a legacy load rewrites as v3.

stdlib-only: imported by the main Carla process (system Python).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from carla_mcp.rig.graph import (
    EDGE_KINDS, NODE_KINDS, Effect, Node, RigGraph, RuntimeUnit,
)

SESSION_FILE = "rig_session.json"
LEGACY_MANIFEST = "rig_manifest.json"
LEGACY_STATE = "rig_state.json"
LOOPER_PROJECT = "project.loopers"


class SessionError(Exception):
    """A rig session could not be read, parsed, or validated."""


@dataclass
class RigSession:
    """Desired state of a whole rig, as read from / written to disk.

    All file references are relative to the session directory.
    """

    name: str
    graph: RigGraph
    carla_project: Optional[str] = None
    looper_session_dir: Optional[str] = None
    version_read: int = 3
    notes: List[str] = field(default_factory=list)


def session_to_dict(sess: RigSession) -> dict:
    """Serialize a RigSession to the v3 JSON shape."""
    nodes = []
    for n in sess.graph.nodes.values():
        entry: dict = {"name": n.name, "kind": n.kind}
        for key in ("instance", "jack_client", "source", "looper_id",
                    "port_index", "port_pattern", "chain_file"):
            value = getattr(n, key)
            if value is not None:
                entry[key] = value
        if n.kind == "app":
            entry["main_muted"] = n.main_muted
            entry["all_muted"] = n.all_muted
        if n.effects:
            entry["effects"] = [
                {"role": e.role, "handle": e.handle, "plugin": e.plugin,
                 "bypassed": e.bypassed}
                for e in n.effects
            ]
        nodes.append(entry)

    edges = []
    for e in sess.graph.edges:
        entry = {"src": e.src, "dst": e.dst, "kind": e.kind, "gain_db": e.gain_db}
        if e.src_port is not None:
            entry["src_port"] = e.src_port
        if e.dst_port is not None:
            entry["dst_port"] = e.dst_port
        edges.append(entry)

    units = []
    for u in sess.graph.runtime_units.values():
        entry = {"name": u.name, "kind": u.kind}
        if u.node is not None:
            entry["node"] = u.node
        units.append(entry)

    return {
        "version": 3,
        "name": sess.name,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "carla_project": sess.carla_project,
        "looper_session_dir": sess.looper_session_dir,
        "nodes": nodes,
        "edges": edges,
        "runtime_units": units,
    }


def session_from_dict(name: str, data: dict) -> RigSession:
    """Build a RigSession from parsed v3 JSON.  Strict: bad input raises."""
    if data.get("version") != 3:
        raise SessionError(f"Unsupported rig_session version: {data.get('version')!r}")
    graph = RigGraph()
    for n in data.get("nodes", []):
        kind = n.get("kind")
        if kind not in NODE_KINDS:
            raise SessionError(f"Node '{n.get('name')}': unknown kind {kind!r}")
        graph.add_node(Node(
            name=n["name"],
            kind=kind,
            instance=n.get("instance"),
            jack_client=n.get("jack_client"),
            source=n.get("source"),
            effects=[
                Effect(handle=e["handle"], role=e["role"], plugin=e["plugin"],
                       bypassed=e.get("bypassed", False))
                for e in n.get("effects", [])
            ],
            looper_id=n.get("looper_id"),
            port_index=n.get("port_index"),
            main_muted=bool(n.get("main_muted", False)),
            all_muted=bool(n.get("all_muted", False)),
            port_pattern=n.get("port_pattern"),
            chain_file=n.get("chain_file"),
        ))
    for e in data.get("edges", []):
        kind = e.get("kind", "audio")
        if kind not in EDGE_KINDS:
            raise SessionError(f"Edge {e.get('src')} -> {e.get('dst')}: unknown kind {kind!r}")
        graph.add_edge(e["src"], e["dst"], gain_db=e.get("gain_db", 0.0),
                       kind=kind, src_port=e.get("src_port"),
                       dst_port=e.get("dst_port"))
    for u in data.get("runtime_units", []):
        graph.add_runtime_unit(RuntimeUnit(name=u["name"], kind=u["kind"],
                                           node=u.get("node")))
    return RigSession(
        name=data.get("name", name),
        graph=graph,
        carla_project=data.get("carla_project"),
        looper_session_dir=data.get("looper_session_dir"),
        version_read=3,
    )


def write_session(sess: RigSession, session_dir: Path) -> Path:
    """Write rig_session.json (v3, the only writable format)."""
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / SESSION_FILE
    path.write_text(json.dumps(session_to_dict(sess), indent=2))
    return path


def read_session(session_dir: Path) -> RigSession:
    """Read a session directory: v3 file preferred, legacy migrated on read."""
    v3_path = session_dir / SESSION_FILE
    if v3_path.exists():
        try:
            data = json.loads(v3_path.read_text())
        except (json.JSONDecodeError, ValueError) as exc:
            raise SessionError(f"{v3_path}: invalid JSON: {exc}") from exc
        return session_from_dict(session_dir.name, data)
    legacy_path = session_dir / LEGACY_MANIFEST
    if legacy_path.exists():
        return _migrate_legacy(session_dir)
    raise SessionError(f"No rig session found at {session_dir}")


def verify_session_files(sess: RigSession, session_dir: Path) -> List[str]:
    """Name every file the session references that does not exist on disk."""
    problems: List[str] = []
    if sess.carla_project and not (session_dir / sess.carla_project).exists():
        problems.append(f"missing file: {sess.carla_project}")
    for node in sess.graph.nodes.values():
        if node.chain_file and not (session_dir / node.chain_file).exists():
            problems.append(f"missing file: {node.chain_file}")
    if sess.looper_session_dir:
        project = session_dir / sess.looper_session_dir / LOOPER_PROJECT
        if not project.exists():
            problems.append(
                f"missing file: {sess.looper_session_dir}/{LOOPER_PROJECT}")
    return problems


def _migrate_legacy(session_dir: Path) -> RigSession:
    raise SessionError(
        f"legacy manifest at {session_dir} — migrator not yet implemented"
    )
