### Task 6: Manifest v3 — `RigSession` read/write + self-verification (`rig/session.py`)

**Files:**
- Create: `source/frontend/carla_mcp/rig/session.py`
- Create: `source/frontend/carla_mcp/tests/test_rig_session_v3.py`

**Interfaces:**
- Produces:
```python
SESSION_FILE = "rig_session.json"
LEGACY_MANIFEST = "rig_manifest.json"
LEGACY_STATE = "rig_state.json"
LOOPER_PROJECT = "project.loopers"

class SessionError(Exception): ...

@dataclass
class RigSession:
    name: str
    graph: RigGraph
    carla_project: Optional[str] = None       # relative to session dir
    looper_session_dir: Optional[str] = None  # relative dir containing project.loopers
    version_read: int = 3
    notes: List[str] = field(default_factory=list)

def session_to_dict(sess: RigSession) -> dict
def session_from_dict(name: str, data: dict) -> RigSession   # raises SessionError
def write_session(sess: RigSession, session_dir: Path) -> Path
def read_session(session_dir: Path) -> RigSession            # v3 or legacy-migrate (Task 7)
def verify_session_files(sess: RigSession, session_dir: Path) -> List[str]
```
- JSON schema v3 (`rig_session.json`), all paths session-relative:
```json
{
  "version": 3,
  "name": "quartet",
  "saved_at": "2026-07-22T12:00:00+00:00",
  "carla_project": "carla_project.carxp",
  "looper_session_dir": "looper",
  "nodes": [
    {"name": "in:guitar", "kind": "endpoint", "jack_client": "alsa_input...:capture_AUX0"},
    {"name": "strat", "kind": "track", "instance": "strat", "jack_client": "CarlaChain_strat",
     "source": "loop:0", "chain_file": "chains/strat.carxp",
     "effects": [{"role": "comp", "handle": "strat/comp", "plugin": "x42-comp", "bypassed": false}]},
    {"name": "loop:0", "kind": "loop", "looper_id": 7, "port_index": 0},
    {"name": "app:looper", "kind": "app", "main_muted": false, "all_muted": false},
    {"name": "midi:pacer", "kind": "midi", "port_pattern": "a2j:.*Pacer.*capture"}
  ],
  "edges": [
    {"src": "loop:0", "dst": "strat", "kind": "audio", "gain_db": 0.0},
    {"src": "midi:pacer", "dst": "app:looper", "kind": "midi",
     "src_port": "a2j:Pacer [32] (capture): Pacer MIDI 1", "dst_port": "loopers:loopers_midi_in"}
  ],
  "runtime_units": [
    {"name": "carla:main", "kind": "carla-main"},
    {"name": "carla:strat", "kind": "carla-child", "node": "strat"},
    {"name": "looper:engine", "kind": "looper-engine"},
    {"name": "looper:mcp", "kind": "looper-mcp"},
    {"name": "a2j", "kind": "a2j"}
  ]
}
```

**Steps:**

- [ ] Write failing test `tests/test_rig_session_v3.py`:

```python
"""Tests for rig/session.py — v3 rig_session.json round-trip and verification."""

import json

import pytest

from carla_mcp.rig.graph import Effect, Node, RigGraph, RuntimeUnit
from carla_mcp.rig.session import (
    SESSION_FILE, RigSession, SessionError, read_session, session_from_dict,
    session_to_dict, verify_session_files, write_session,
)


def _session():
    g = RigGraph()
    g.add_node(Node(name="loop:0", kind="loop", looper_id=7, port_index=0))
    g.add_node(Node(name="strat", kind="track", instance="strat",
                    jack_client="CarlaChain_strat", source="loop:0",
                    chain_file="chains/strat.carxp",
                    effects=[Effect(handle="strat/comp", role="comp", plugin="x42-comp")]))
    g.add_node(Node(name="out:main", kind="endpoint"))
    g.add_node(Node(name="app:looper", kind="app", main_muted=True))
    g.add_node(Node(name="midi:pacer", kind="midi", port_pattern=r"a2j:.*Pacer.*capture"))
    g.add_edge("loop:0", "strat")
    g.add_edge("strat", "out:main", gain_db=-3.0)
    g.add_edge("midi:pacer", "app:looper", kind="midi")
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
    g.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
    return RigSession(name="t", graph=g, carla_project="carla_project.carxp",
                      looper_session_dir="looper")


class TestRoundTrip:
    def test_write_then_read_preserves_everything(self, tmp_path):
        sdir = tmp_path / "t"
        sdir.mkdir()
        write_session(_session(), sdir)
        sess = read_session(sdir)
        assert sess.version_read == 3
        g = sess.graph
        assert g.get_node("loop:0").looper_id == 7
        assert g.get_node("strat").chain_file == "chains/strat.carxp"
        assert g.get_node("strat").effects[0].handle == "strat/comp"
        assert g.get_node("app:looper").main_muted is True
        assert g.get_node("midi:pacer").port_pattern == r"a2j:.*Pacer.*capture"
        kinds = {(e.src, e.dst): e.kind for e in g.edges}
        assert kinds[("midi:pacer", "app:looper")] == "midi"
        gains = {(e.src, e.dst): e.gain_db for e in g.edges}
        assert gains[("strat", "out:main")] == -3.0
        assert set(g.runtime_units) == {"carla:main", "carla:strat", "looper:engine"}
        assert sess.carla_project == "carla_project.carxp"
        assert sess.looper_session_dir == "looper"

    def test_written_file_is_version_3(self, tmp_path):
        sdir = tmp_path / "t"
        sdir.mkdir()
        path = write_session(_session(), sdir)
        data = json.loads(path.read_text())
        assert path.name == SESSION_FILE
        assert data["version"] == 3
        assert data["saved_at"]

    def test_explicit_port_edge_round_trips(self, tmp_path):
        sess = _session()
        sess.graph.add_node(Node(name="cap", kind="endpoint", jack_client="alsa_input.x:capture_AUX0"))
        sess.graph.add_edge("cap", "loop:0",
                            src_port="alsa_input.x:capture_AUX0",
                            dst_port="loopers:loop0_in_l")
        sdir = tmp_path / "t"
        sdir.mkdir()
        write_session(sess, sdir)
        back = read_session(sdir)
        e = [e for e in back.graph.edges if e.src == "cap"][0]
        assert (e.src_port, e.dst_port) == ("alsa_input.x:capture_AUX0", "loopers:loop0_in_l")


class TestStrictness:
    def test_unknown_version_raises(self, tmp_path):
        sdir = tmp_path / "t"
        sdir.mkdir()
        (sdir / SESSION_FILE).write_text(json.dumps({"version": 9, "nodes": []}))
        with pytest.raises(SessionError, match="version"):
            read_session(sdir)

    def test_bad_json_raises(self, tmp_path):
        sdir = tmp_path / "t"
        sdir.mkdir()
        (sdir / SESSION_FILE).write_text("{nope")
        with pytest.raises(SessionError):
            read_session(sdir)

    def test_missing_session_raises(self, tmp_path):
        with pytest.raises(SessionError, match="No rig session"):
            read_session(tmp_path / "absent")

    def test_bad_node_kind_raises(self):
        with pytest.raises(SessionError, match="kind"):
            session_from_dict("t", {"version": 3,
                                    "nodes": [{"name": "x", "kind": "banana"}],
                                    "edges": [], "runtime_units": []})


class TestVerifySessionFiles:
    def test_all_present_is_clean(self, tmp_path):
        sdir = tmp_path / "t"
        (sdir / "chains").mkdir(parents=True)
        (sdir / "looper").mkdir()
        (sdir / "carla_project.carxp").write_text("<carla/>")
        (sdir / "chains" / "strat.carxp").write_text("<carla/>")
        (sdir / "looper" / "project.loopers").write_text("{}")
        assert verify_session_files(_session(), sdir) == []

    def test_every_missing_file_named(self, tmp_path):
        sdir = tmp_path / "t"
        sdir.mkdir()
        problems = "\n".join(verify_session_files(_session(), sdir))
        assert "carla_project.carxp" in problems
        assert "chains/strat.carxp" in problems
        assert "looper/project.loopers" in problems
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_session_v3.py -v` — expect `ModuleNotFoundError: No module named 'carla_mcp.rig.session'`.
- [ ] Implement `rig/session.py` (v3 only; `read_session` raises `SessionError` for legacy manifests until Task 7 adds `_migrate_legacy`):

```python
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
```

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_session_v3.py -v`
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/session.py source/frontend/carla_mcp/tests/test_rig_session_v3.py
git commit -m "feat(rig): manifest v3 RigSession read/write with strict validation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

