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
