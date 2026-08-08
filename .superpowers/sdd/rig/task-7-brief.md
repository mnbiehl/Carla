### Task 7: Read-time migrator for v1/v2 sessions (`rig/session.py` part 2)

**Files:**
- Modify: `source/frontend/carla_mcp/rig/session.py` (replace `_migrate_legacy` stub; add helpers)
- Create: `source/frontend/carla_mcp/tests/test_rig_session_migrate.py`

**Interfaces:**
- Consumes real-world legacy shapes (verified on disk under `~/.config/rig-sessions/`):
  - v1 `rig_manifest.json`: `{"version": 1, "backends": {"carla": {"running", "session": "<abs .carxp>"}, "looper": {"running", "session": "<abs path>"}}}` — the looper `"session"` path is a **directory** containing an auto-named subdir (e.g. `2026-04-03_17:18:42/`) holding `project.loopers` + WAVs.
  - v2 `rig_manifest.json`: v1 plus `"routing": [[src, dst], ...]` flat pw-link pairs.
  - Optional `rig_state.json` (export_rig_state v1): `{"version": 1, "nodes": [{name, kind, instance, jack_client, source, effects, chain_file(abs)}], "edges": [{src, dst, gain_db}]}`.
  - `project.loopers`: `{"loopers": [{"id", "input_source": {"Mono": {"port": ...}} | null, ...}]}` — file position = port index.
- Produces: `_migrate_legacy(session_dir) -> RigSession` plus helpers `_find_looper_project`, `_lift_rig_state`, `_lift_looper_inputs`, `_ensure_port_endpoint`. Migration notes record the source version and every unliftable item.

**Steps:**

- [ ] Write failing test `tests/test_rig_session_migrate.py`:

```python
"""Tests for the v1/v2 -> v3 read-time migrator.

Fixtures replicate the shapes of the five real sessions in
~/.config/rig-sessions/: v1 manifest only; v1 + rig_state.json;
v1 + auto-named looper subdir; v2 with flat routing pairs.
"""

import json

from carla_mcp.rig.session import read_session

CAPTURE = "Focusrite Scarlett 2i2 2nd Gen Pro:capture_AUX0"


def _write_v1_manifest(sdir, looper=True):
    manifest = {
        "version": 1,
        "backends": {
            "carla": {"running": True, "session": str(sdir / "carla_project.carxp")},
            "looper": {"running": looper,
                       "session": str(sdir / "looper_session.json") if looper else ""},
        },
    }
    (sdir / "rig_manifest.json").write_text(json.dumps(manifest))
    (sdir / "carla_project.carxp").write_text("<carla/>")


def _write_looper_project(sdir, autodir="2026-04-03_17:18:42"):
    d = sdir / "looper_session.json" / autodir
    d.mkdir(parents=True)
    project = {
        "loopers": [
            {"id": 3, "mode": "Playing", "pan": 0.0, "level": 1.0,
             "input_source": {"Mono": {"port": CAPTURE, "display_name": "x"}}},
            {"id": 1, "mode": "Playing", "pan": 1.0, "level": 1.0,
             "input_source": None},
        ]
    }
    (d / "project.loopers").write_text(json.dumps(project))
    return d


class TestV1LooperSession:
    def test_migrates_and_finds_autonamed_subdir(self, tmp_path):
        sdir = tmp_path / "full-rig"
        sdir.mkdir()
        _write_v1_manifest(sdir)
        auto = _write_looper_project(sdir)
        sess = read_session(sdir)
        assert sess.version_read == 1
        assert sess.carla_project == "carla_project.carxp"
        assert sess.looper_session_dir == str(auto.relative_to(sdir))
        assert sess.graph.has_node("app:looper")
        assert "looper:engine" in sess.graph.runtime_units
        assert "carla:main" in sess.graph.runtime_units

    def test_loop_nodes_created_by_file_position(self, tmp_path):
        sdir = tmp_path / "s"
        sdir.mkdir()
        _write_v1_manifest(sdir)
        _write_looper_project(sdir)
        sess = read_session(sdir)
        assert sess.graph.get_node("loop:0").looper_id == 3
        assert sess.graph.get_node("loop:1").looper_id == 1

    def test_mono_input_source_lifted_to_edge(self, tmp_path):
        sdir = tmp_path / "s"
        sdir.mkdir()
        _write_v1_manifest(sdir)
        _write_looper_project(sdir)
        sess = read_session(sdir)
        edges = {(e.src, e.dst) for e in sess.graph.edges}
        assert (CAPTURE, "loop:0") in edges
        assert sess.graph.get_node(CAPTURE).kind == "endpoint"

    def test_v1_no_routing_note_recorded(self, tmp_path):
        sdir = tmp_path / "s"
        sdir.mkdir()
        _write_v1_manifest(sdir)
        _write_looper_project(sdir)
        sess = read_session(sdir)
        assert any("v1" in n for n in sess.notes)

    def test_missing_looper_project_named_in_notes(self, tmp_path):
        sdir = tmp_path / "s"
        sdir.mkdir()
        _write_v1_manifest(sdir)  # looper session referenced but dir absent
        sess = read_session(sdir)
        assert sess.looper_session_dir is None
        assert any("project.loopers" in n for n in sess.notes)


class TestRigStateLifting:
    def test_track_nodes_edges_and_child_units_lifted(self, tmp_path):
        sdir = tmp_path / "quartet"
        sdir.mkdir()
        _write_v1_manifest(sdir, looper=False)
        state = {
            "version": 1,
            "nodes": [
                {"name": "loopers:loop0_out", "kind": "endpoint", "instance": None,
                 "jack_client": "loopers:loop0_out", "source": None, "effects": []},
                {"name": "rhythm", "kind": "track", "instance": "rhythm",
                 "jack_client": "CarlaChain_rhythm", "source": "loopers:loop0_out",
                 "effects": [{"role": "eq", "handle": "rhythm/eq",
                              "plugin": "x42-eq", "bypassed": False}],
                 "chain_file": str(sdir / "chains" / "rhythm.carxp")},
            ],
            "edges": [{"src": "loopers:loop0_out", "dst": "rhythm", "gain_db": 0.0}],
        }
        (sdir / "rig_state.json").write_text(json.dumps(state))
        sess = read_session(sdir)
        g = sess.graph
        # loopers:loop0_out endpoint is normalized into a loop:0 node
        assert g.has_node("loop:0")
        assert not g.has_node("loopers:loop0_out")
        assert {(e.src, e.dst) for e in g.edges} == {("loop:0", "rhythm")}
        assert g.get_node("rhythm").chain_file == "chains/rhythm.carxp"
        assert g.get_node("rhythm").effects[0].handle == "rhythm/eq"
        assert g.runtime_units["carla:rhythm"].kind == "carla-child"


class TestV2Routing:
    def test_flat_pairs_become_explicit_port_edges(self, tmp_path):
        sdir = tmp_path / "v2"
        sdir.mkdir()
        manifest = {
            "version": 2,
            "backends": {
                "carla": {"running": True, "session": str(sdir / "carla_project.carxp")},
                "looper": {"running": False, "session": ""},
            },
            "routing": [
                ["loopers:loop0_out_l", "Carla:audio-in3"],
                ["loopers:loop0_out_r", "Carla:audio-in4"],
            ],
        }
        (sdir / "rig_manifest.json").write_text(json.dumps(manifest))
        (sdir / "carla_project.carxp").write_text("<carla/>")
        sess = read_session(sdir)
        ports = {(e.src_port, e.dst_port) for e in sess.graph.edges}
        assert ("loopers:loop0_out_l", "Carla:audio-in3") in ports
        assert ("loopers:loop0_out_r", "Carla:audio-in4") in ports

    def test_malformed_routing_entry_named_not_dropped(self, tmp_path):
        sdir = tmp_path / "v2"
        sdir.mkdir()
        manifest = {
            "version": 2,
            "backends": {"carla": {"running": False, "session": ""},
                         "looper": {"running": False, "session": ""}},
            "routing": [["only-one-element"]],
        }
        (sdir / "rig_manifest.json").write_text(json.dumps(manifest))
        sess = read_session(sdir)
        assert any("unliftable routing entry" in n for n in sess.notes)
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_session_migrate.py -v` — expect `SessionError: legacy manifest ... migrator not yet implemented`.
- [ ] Replace `_migrate_legacy` in `rig/session.py`:

```python
_LOOP_ENDPOINT_RE = __import__("re").compile(r"^loopers:loop(\d+)_(out|in)$")


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
```

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_session_migrate.py source/frontend/carla_mcp/tests/test_rig_session_v3.py -v`
- [ ] Manually smoke-check the real sessions (read-only, no writes):
  `uv run python -c "from pathlib import Path; from carla_mcp.rig.session import read_session; [print(d.name, '->', len(read_session(d).graph.nodes), 'nodes,', len(read_session(d).graph.edges), 'edges') for d in sorted(Path.home().joinpath('.config/rig-sessions').iterdir()) if d.is_dir()]"` (run with `PYTHONPATH=source/frontend`); all five must load without raising.
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/session.py source/frontend/carla_mcp/tests/test_rig_session_migrate.py
git commit -m "feat(rig): read-time v1/v2 session migrator with input_source lifting

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

