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
import re
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


_LOOP_ENDPOINT_RE = re.compile(r"^loopers:loop(\d+)_(out|in)$")


def _migrate_legacy(session_dir: Path) -> RigSession:
    """Convert a v1/v2 session (rig_manifest.json et al.) to a v3 RigSession.

    Read-only migration: nothing on disk changes; the first save after a
    legacy load rewrites as v3.  Every unliftable item is named in notes.
    """
    manifest_path = session_dir / LEGACY_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, ValueError) as exc:
        raise SessionError(f"{manifest_path}: invalid JSON: {exc}") from exc

    version = manifest.get("version", 1)
    graph = RigGraph()
    notes: List[str] = [f"migrated from legacy manifest v{version}"]
    if version == 1:
        notes.append(
            "v1 manifest: no saved pw-link routing; only edges implied by "
            "rig_state.json and looper input sources were lifted"
        )
    sess = RigSession(name=session_dir.name, graph=graph,
                      version_read=version, notes=notes)

    backends = manifest.get("backends", {})

    carla_cfg = backends.get("carla", {})
    if carla_cfg.get("session"):
        sess.carla_project = Path(carla_cfg["session"]).name
        graph.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))

    state_path = session_dir / LEGACY_STATE
    if state_path.exists():
        try:
            _lift_rig_state(json.loads(state_path.read_text()),
                            graph, session_dir, notes)
        except (json.JSONDecodeError, ValueError) as exc:
            notes.append(f"rig_state.json unreadable, per-track chains lost: {exc}")

    looper_cfg = backends.get("looper", {})
    if looper_cfg.get("session"):
        base = session_dir / Path(looper_cfg["session"]).name
        project_path = _find_looper_project(base)
        if project_path is None:
            notes.append(
                f"looper session referenced ({looper_cfg['session']}) but no "
                f"{LOOPER_PROJECT} found under it"
            )
        else:
            sess.looper_session_dir = str(project_path.parent.relative_to(session_dir))
            if not graph.has_node("app:looper"):
                graph.add_node(Node(name="app:looper", kind="app"))
            graph.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
            graph.add_runtime_unit(RuntimeUnit(name="looper:mcp", kind="looper-mcp"))
            try:
                _lift_looper_inputs(json.loads(project_path.read_text()), graph, notes)
            except (json.JSONDecodeError, ValueError) as exc:
                notes.append(f"{LOOPER_PROJECT} unreadable, input edges lost: {exc}")

    for entry in manifest.get("routing", []) or []:
        try:
            src, dst = entry
        except (TypeError, ValueError):
            notes.append(f"unliftable routing entry: {entry!r}")
            continue
        _ensure_port_endpoint(graph, src)
        _ensure_port_endpoint(graph, dst)
        graph.add_edge(src, dst, kind="audio", src_port=src, dst_port=dst)

    return sess


def _find_looper_project(base: Path) -> Optional[Path]:
    """Find project.loopers under *base*, tolerating the auto-named subdir."""
    direct = base / LOOPER_PROJECT
    if direct.exists():
        return direct
    if base.is_dir():
        for sub in sorted(p for p in base.iterdir() if p.is_dir()):
            candidate = sub / LOOPER_PROJECT
            if candidate.exists():
                return candidate
    return None


def _lift_rig_state(state: dict, graph: RigGraph, session_dir: Path,
                    notes: List[str]) -> None:
    """Lift an export_rig_state v1 dict into the graph, normalizing loop
    endpoints (loopers:loopN_out) into loop:N nodes."""
    rename: dict = {}
    for n in state.get("nodes", []):
        name = n["name"]
        m = _LOOP_ENDPOINT_RE.match(n.get("jack_client") or name)
        if n.get("kind") == "endpoint" and m:
            idx = int(m.group(1))
            loop_name = f"loop:{idx}"
            rename[name] = loop_name
            if not graph.has_node(loop_name):
                graph.add_node(Node(name=loop_name, kind="loop", port_index=idx))
            continue
        chain_file = n.get("chain_file")
        if chain_file:
            p = Path(chain_file)
            try:
                chain_file = str(p.relative_to(session_dir))
            except ValueError:
                notes.append(f"{name}: chain file outside session dir kept absolute: {chain_file}")
        if not graph.has_node(name):
            graph.add_node(Node(
                name=name, kind=n.get("kind", "endpoint"),
                instance=n.get("instance"), jack_client=n.get("jack_client"),
                source=rename.get(n.get("source"), n.get("source")),
                chain_file=chain_file,
                effects=[
                    Effect(handle=e["handle"], role=e["role"], plugin=e["plugin"],
                           bypassed=e.get("bypassed", False))
                    for e in n.get("effects", [])
                ],
            ))
        if n.get("kind") in ("track", "bus"):
            graph.add_runtime_unit(RuntimeUnit(
                name=f"carla:{name}", kind="carla-child", node=name))
    # second pass: fix sources that referenced renamed loop endpoints
    for node in graph.nodes.values():
        if node.source in rename:
            node.source = rename[node.source]
    for e in state.get("edges", []):
        src = rename.get(e["src"], e["src"])
        dst = rename.get(e["dst"], e["dst"])
        if not (graph.has_node(src) and graph.has_node(dst)):
            notes.append(f"edge {e['src']} -> {e['dst']}: endpoint missing, not lifted")
            continue
        graph.add_edge(src, dst, gain_db=e.get("gain_db", 0.0))


def _lift_looper_inputs(project: dict, graph: RigGraph, notes: List[str]) -> None:
    """Create loop:N nodes from the looper project (file position = port
    index) and lift each input_source into a capture->loop edge."""
    for idx, lp in enumerate(project.get("loopers", []) or []):
        loop_name = f"loop:{idx}"
        if not graph.has_node(loop_name):
            graph.add_node(Node(name=loop_name, kind="loop",
                                looper_id=lp.get("id"), port_index=idx))
        else:
            node = graph.get_node(loop_name)
            node.looper_id = lp.get("id")
            node.port_index = idx
        source = lp.get("input_source")
        if not source:
            continue
        if isinstance(source, dict) and "Mono" in source:
            port = (source["Mono"] or {}).get("port")
            if not port:
                notes.append(f"loop:{idx}: Mono input_source without port, not lifted")
                continue
            _ensure_port_endpoint(graph, port)
            graph.add_edge(port, loop_name, kind="audio")
        elif isinstance(source, dict) and "Stereo" in source:
            stereo = source["Stereo"] or {}
            left = stereo.get("left_port") or (stereo.get("left") or {}).get("port")
            right = stereo.get("right_port") or (stereo.get("right") or {}).get("port")
            if not (left and right):
                notes.append(f"loop:{idx}: Stereo input_source shape not liftable: {stereo!r}")
                continue
            for port, side in ((left, "l"), (right, "r")):
                _ensure_port_endpoint(graph, port)
                graph.add_edge(port, loop_name, kind="audio", src_port=port,
                               dst_port=f"loopers:loop{idx}_in_{side}")
        else:
            notes.append(f"loop:{idx}: unknown input_source shape: {source!r}")


def _ensure_port_endpoint(graph: RigGraph, port: str) -> None:
    """Ensure an endpoint node exists whose name and jack_client are *port*."""
    if not graph.has_node(port):
        graph.add_node(Node(name=port, kind="endpoint", jack_client=port))
