### Task 10: Converge engine — self-verifying `do_save` with live-link lifting

**Files:**
- Modify: `source/frontend/carla_mcp/rig/converge.py` (append)
- Create: `source/frontend/carla_mcp/tests/test_rig_converge_save.py`

**Interfaces:**
- Produces:
```python
def _graph_from_export(export: dict, graph: RigGraph, session_dir: Path, notes: List[str]) -> None
    # nodes/edges/effects/chain_file(relativized) + carla:<node> child units;
    # loopers:loopN_out endpoints normalized to loop:N (reuses session._lift_rig_state)
def _lift_link(graph: RigGraph, src: str, dst: str, notes: List[str]) -> None
    # uncovered live rig-space link -> explicit-port edge; known schemas map to
    # loop:N / app:looper / track nodes; a2j midi source creates midi:pacer node
    # (port_pattern = re.escape(src)) and an "a2j" runtime unit; unknown ports
    # become exact-name endpoint nodes
async def do_save(name: str, session_dir: Path, ops: RigOps) -> str
```
- Save sequence: `export_rig_state(chains)` → `_graph_from_export` → `save_carla_project` → `looper_get_state` (loop nodes via `loop_nodes_from_looper_state`, `app:looper` node with `main_muted`/`all_muted` from GetState top level, looper units) → `looper_save_session_at(<dir>/looper)` → observe + lift uncovered rig-space links → `write_session` → **self-verify** (re-read via `read_session`, `verify_session_files`) → report. `FAILED:` when neither Carla nor looper produced state or the re-read fails; every skipped/unliftable item in Notes.

**Steps:**

- [ ] Write failing test `tests/test_rig_converge_save.py`:

```python
"""Tests for rig/converge.do_save — v3 emit + self-verification + link lifting."""

import asyncio
import json
from pathlib import Path

from carla_mcp.rig.converge import RigOps, do_save
from carla_mcp.rig.observe import Link, ObservedState
from carla_mcp.rig.session import read_session

MON0 = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"
CAPTURE = "alsa_input.usb-F-00.pro-input-0:capture_AUX0"
PACER = "a2j:Pacer [32] (capture): Pacer MIDI 1"
MIDI_IN = "loopers:loopers_midi_in"


class SaveFakeOps(RigOps):
    def __init__(self):
        self.outputs = ["loopers:loop0_out_l", "loopers:loop0_out_r",
                        "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2",
                        CAPTURE, PACER]
        self.inputs = ["loopers:loop0_in_l", "loopers:loop0_in_r",
                       "CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
                       MIDI_IN, MON0]
        self.links = [
            Link("loopers:loop0_out_l", "CarlaChain_strat:audio-in1"),
            Link("loopers:loop0_out_r", "CarlaChain_strat:audio-in2"),
            Link(CAPTURE, "loopers:loop0_in_l"),
            Link(CAPTURE, "loopers:loop0_in_r"),
            Link(PACER, MIDI_IN),
        ]

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph else []
        return ObservedState(links=self.links, output_ports=self.outputs,
                             input_ports=self.inputs,
                             unit_status={u.name: True for u in units})

    async def export_rig_state(self, chains_dir):
        Path(chains_dir).mkdir(parents=True, exist_ok=True)
        chain = Path(chains_dir) / "strat.carxp"
        chain.write_text("<carla/>")
        return {
            "version": 1,
            "nodes": [
                {"name": "loopers:loop0_out", "kind": "endpoint", "instance": None,
                 "jack_client": "loopers:loop0_out", "source": None, "effects": []},
                {"name": "strat", "kind": "track", "instance": "strat",
                 "jack_client": "CarlaChain_strat", "source": "loopers:loop0_out",
                 "effects": [{"role": "eq", "handle": "strat/eq",
                              "plugin": "x42-eq", "bypassed": False}],
                 "chain_file": str(chain)},
            ],
            "edges": [{"src": "loopers:loop0_out", "dst": "strat", "gain_db": 0.0}],
            "errors": [],
        }

    async def save_carla_project(self, path):
        Path(path).write_text("<carla/>")
        return None

    async def looper_get_state(self):
        return {"main_muted": True, "all_muted": False,
                "loopers": [{"id": 7, "port_index": 0, "mode": "Playing",
                             "level_db": 0.0, "pan": 0.0, "input_source": None}]}

    async def looper_save_session_at(self, dir_path):
        d = Path(dir_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.loopers").write_text(json.dumps({"loopers": []}))
        return None


class TestDoSave:
    def test_save_emits_verified_v3(self, tmp_path):
        sdir = tmp_path / "s"
        report = asyncio.run(do_save("s", sdir, SaveFakeOps()))
        assert report.splitlines()[0] == "OK", report
        sess = read_session(sdir)
        assert sess.carla_project == "carla_project.carxp"
        assert sess.looper_session_dir == "looper"
        assert sess.graph.get_node("loop:0").looper_id == 7
        assert sess.graph.get_node("app:looper").main_muted is True
        assert sess.graph.get_node("strat").chain_file == "chains/strat.carxp"

    def test_loop_edge_normalized_not_duplicated(self, tmp_path):
        sdir = tmp_path / "s"
        asyncio.run(do_save("s", sdir, SaveFakeOps()))
        sess = read_session(sdir)
        loop_edges = [e for e in sess.graph.edges
                      if e.src == "loop:0" and e.dst == "strat"]
        assert len(loop_edges) == 1
        # covered live links must NOT be lifted as explicit-port duplicates
        explicit = [e for e in sess.graph.edges
                    if e.src_port == "loopers:loop0_out_l"]
        assert explicit == []

    def test_capture_and_midi_links_lifted(self, tmp_path):
        sdir = tmp_path / "s"
        asyncio.run(do_save("s", sdir, SaveFakeOps()))
        sess = read_session(sdir)
        lifted = {(e.src_port, e.dst_port) for e in sess.graph.edges if e.src_port}
        assert (CAPTURE, "loopers:loop0_in_l") in lifted
        assert (CAPTURE, "loopers:loop0_in_r") in lifted
        assert (PACER, MIDI_IN) in lifted
        pacer_nodes = [n for n in sess.graph.nodes.values() if n.kind == "midi"]
        assert len(pacer_nodes) == 1
        assert "a2j" in sess.graph.runtime_units

    def test_nothing_running_is_failed(self, tmp_path):
        class DeadOps(SaveFakeOps):
            async def export_rig_state(self, chains_dir):
                return None
            async def looper_get_state(self):
                return None
            async def observe(self, graph):
                return ObservedState()
        report = asyncio.run(do_save("s", tmp_path / "s", DeadOps()))
        assert report.startswith("FAILED:")

    def test_missing_referenced_file_degrades(self, tmp_path):
        class NoChainOps(SaveFakeOps):
            async def export_rig_state(self, chains_dir):
                export = await super().export_rig_state(chains_dir)
                # simulate a child whose save failed: file never written
                Path(export["nodes"][1]["chain_file"]).unlink()
                return export
        report = asyncio.run(do_save("s", tmp_path / "s", NoChainOps()))
        assert report.startswith("DEGRADED:")
        assert "chains/strat.carxp" in report
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_rig_converge_save.py -v` — expect `ImportError: cannot import name 'do_save'`.
- [ ] Append to `rig/converge.py` (imports: add `import re` at top; `LOOPER_MIDI_IN` comes from `reconcile`, already imported):

```python
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


async def do_save(name: str, session_dir: Path, ops: RigOps) -> str:
    """Capture the live rig as a v3 session and verify the written output."""
    notes: List[str] = []
    session_dir.mkdir(parents=True, exist_ok=True)
    graph = RigGraph()
    carla_project: Optional[str] = None
    looper_dir: Optional[str] = None

    export = await ops.export_rig_state(str(session_dir / "chains"))
    if export is not None:
        _graph_from_export(export, graph, session_dir, notes)
        err = await ops.save_carla_project(str(session_dir / "carla_project.carxp"))
        if err is None:
            carla_project = "carla_project.carxp"
        else:
            notes.append(f"carla project save: {err}")
        graph.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    else:
        notes.append("carla not reachable; no Carla state saved")

    state = await ops.looper_get_state()
    if state is not None:
        for loop_node in loop_nodes_from_looper_state(state):
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
        return f"FAILED: nothing to save (carla and looper both unreachable)"

    # Lift every live rig-space link not covered by graph edges.
    observed = await ops.observe(graph)
    expansion = expand_edges(graph, observed.output_ports, observed.input_ports)
    covered = {(p.src, p.dst) for p in expansion.pairs}
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
                             [("Notes", notes)])
    problems = verify_session_files(reread, session_dir)
    issues = problems + notes
    verdict = "OK" if not issues else f"DEGRADED: {len(issues)} issues"
    return render_report(verdict, [("Problems", problems), ("Notes", notes)])
```

- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_rig_converge_save.py -v`
- [ ] Commit:
```
git add source/frontend/carla_mcp/rig/converge.py source/frontend/carla_mcp/tests/test_rig_converge_save.py
git commit -m "feat(rig): self-verifying do_save with live rig-space link lifting

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

