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
