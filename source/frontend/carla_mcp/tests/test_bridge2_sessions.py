import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.tools import lifecycle, sessions
from carla_mcp.rig.graph import RigGraph, RuntimeUnit
from carla_mcp.rig.observe import ObservedState
from carla_mcp.rig.session import RigSession, write_session

INVALID_NAMES = ["../x", "/abs", "a/b", "", ".hidden", ".."]


def _bridge():
    b = Bridge.for_tests()
    b.looper.loopers = AsyncMock(return_value=[])
    b.carla.version = AsyncMock(return_value={"worker": "w"})
    return b


def _tools(b):
    return {t.name: t for t in sessions.build(b)}


def _lifecycle_tools(b):
    return {t.name: t for t in lifecycle.build(b)}


def _seed(b, name):
    g = RigGraph()
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    d = b.config.session_dir / name
    d.mkdir(parents=True)
    write_session(RigSession(name=name, graph=g), d)
    return d


def _snapshot(session_dir):
    if not session_dir.exists():
        return []
    return sorted(str(p) for p in session_dir.rglob("*"))


def test_session_list_only_real_sessions():
    b = _bridge()
    _seed(b, "b-jam"); _seed(b, "a-jam")
    (b.config.session_dir / "junk").mkdir()
    assert asyncio.run(_tools(b)["session_list"].fn())["result"] == ["a-jam", "b-jam"]


def test_session_load_sets_graph_and_returns_state():
    b = _bridge()
    _seed(b, "tues")
    empty = ObservedState(links=[], output_ports=[], input_ports=[], unit_status={"carla:main": True})
    with patch("carla_mcp.bridge.tools.sessions.do_load", new=AsyncMock(return_value="OK\n")) as load, \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=empty)):
        out = asyncio.run(_tools(b)["session_load"].fn("tues"))
    assert out["ok"] and out["result"]["report"] == "OK\n" and out["result"]["state"]["session"] == "tues"
    assert b.session_name == "tues" and b.graph is not None
    assert load.await_args.args[0] == "tues"


def test_session_load_missing_is_not_found():
    out = asyncio.run(_tools(_bridge())["session_load"].fn("ghost"))
    assert out["ok"] is False and out["error"]["type"] == "not_found"


def test_session_save_refuses_overwrite_then_saves():
    b = _bridge()
    d = _seed(b, "tues")
    out = asyncio.run(_tools(b)["session_save"].fn("tues"))
    assert out["ok"] is False and out["error"]["type"] == "validation"

    async def fake_save(name, sdir, ops):
        (sdir / "looper").mkdir(exist_ok=True)
        (sdir / "looper" / "project.loopers").write_text("{}")
        return "OK\n"

    with patch("carla_mcp.bridge.tools.sessions.do_save", new=fake_save):
        out = asyncio.run(_tools(b)["session_save"].fn("tues", overwrite=True))
    assert out["ok"] and out["result"]["path"] == str(d) and b.session_name == "tues"


def test_annotations():
    t = _tools(_bridge())
    assert t["session_load"].annotations == {"destructiveHint": True}
    assert t["session_list"].annotations == {"readOnlyHint": True}
    assert t["session_save"].annotations == {}


# ----- session name validation (no path escape) ---------------------------

@pytest.mark.parametrize("name", INVALID_NAMES)
def test_session_save_rejects_invalid_names(name):
    b = _bridge()
    before = _snapshot(b.config.session_dir)

    async def unreachable_save(name, sdir, ops):
        raise AssertionError("do_save must not run for an invalid session name")

    with patch("carla_mcp.bridge.tools.sessions.do_save", new=unreachable_save):
        out = asyncio.run(_tools(b)["session_save"].fn(name, overwrite=True))
    assert out["ok"] is False and out["error"]["type"] == "validation"
    assert _snapshot(b.config.session_dir) == before


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_session_load_rejects_invalid_names(name):
    b = _bridge()
    before = _snapshot(b.config.session_dir)

    async def unreachable_load(name, sdir, ops):
        raise AssertionError("do_load must not run for an invalid session name")

    with patch("carla_mcp.bridge.tools.sessions.do_load", new=unreachable_load):
        out = asyncio.run(_tools(b)["session_load"].fn(name))
    assert out["ok"] is False and out["error"]["type"] == "validation"
    assert _snapshot(b.config.session_dir) == before


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_rig_state_compare_rejects_invalid_names(name):
    b = _bridge()
    empty = ObservedState(links=[], output_ports=[], input_ports=[], unit_status={})
    before = _snapshot(b.config.session_dir)
    with patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=empty)):
        out = asyncio.run(_lifecycle_tools(b)["rig_state"].fn(compare=name))
    assert out["ok"] is False and out["error"]["type"] == "validation"
    assert _snapshot(b.config.session_dir) == before


def test_session_path_accepts_a_valid_name():
    b = _bridge()
    d = _seed(b, "tues-jam")
    assert sessions.session_path(b, "tues-jam") == d


# ----- FAILED saves are errors and leave no empty directory behind -----------

NOTHING = "FAILED: nothing to save (carla and looper both unreachable)"


def test_failed_save_on_fresh_dir_is_degraded_error_and_removes_the_dir():
    b = _bridge()
    sdir = b.config.session_dir / "tues"

    async def failing_save(name, d, ops):
        d.mkdir(parents=True, exist_ok=True)  # what do_save does before giving up
        return NOTHING

    with patch("carla_mcp.bridge.tools.sessions.do_save", new=failing_save):
        out = asyncio.run(_tools(b)["session_save"].fn("tues"))
    assert out["ok"] is False and out["error"] == {"type": "degraded", "message": NOTHING}
    assert not sdir.exists()
    assert b.graph is None and b.session_name is None
    # The name is free again: a re-save is not refused as "exists".
    with patch("carla_mcp.bridge.tools.sessions.do_save", new=failing_save):
        again = asyncio.run(_tools(b)["session_save"].fn("tues"))
    assert again["error"]["type"] == "degraded"


def test_failed_save_through_real_do_save_with_backends_down_removes_the_dir():
    b = _bridge()  # for_tests ports refuse immediately: carla and looper unreachable
    out = asyncio.run(_tools(b)["session_save"].fn("tues"))
    assert out["ok"] is False and out["error"] == {"type": "degraded", "message": NOTHING}
    assert not (b.config.session_dir / "tues").exists()


def test_failed_overwrite_leaves_existing_dir_untouched():
    b = _bridge()
    sdir = _seed(b, "tues")
    before = _snapshot(sdir)

    async def failing_save(name, d, ops):
        return NOTHING

    with patch("carla_mcp.bridge.tools.sessions.do_save", new=failing_save):
        out = asyncio.run(_tools(b)["session_save"].fn("tues", overwrite=True))
    assert out["ok"] is False and out["error"]["type"] == "degraded"
    assert sdir.is_dir() and _snapshot(sdir) == before
    assert b.graph is None and b.session_name is None


def test_failed_overwrite_of_existing_empty_dir_is_not_removed():
    b = _bridge()
    sdir = b.config.session_dir / "tues"
    sdir.mkdir(parents=True)

    async def failing_save(name, d, ops):
        return NOTHING

    with patch("carla_mcp.bridge.tools.sessions.do_save", new=failing_save):
        out = asyncio.run(_tools(b)["session_save"].fn("tues", overwrite=True))
    assert out["error"]["type"] == "degraded" and sdir.is_dir()


def test_failed_save_that_wrote_files_keeps_them_and_reports_the_full_report():
    b = _bridge()
    sdir = b.config.session_dir / "tues"
    report = "FAILED: saved session does not re-read: bad json\n[Notes]\n  carla not reachable"

    async def failing_save(name, d, ops):
        d.mkdir(parents=True)
        (d / "rig_session.json").write_text("{")
        return report

    with patch("carla_mcp.bridge.tools.sessions.do_save", new=failing_save):
        out = asyncio.run(_tools(b)["session_save"].fn("tues"))
    assert out["error"] == {"type": "degraded", "message": "FAILED: saved session does not re-read: bad json"}
    assert out["notes"] == [report]
    assert (sdir / "rig_session.json").exists()


def test_degraded_save_is_ok_with_report():
    b = _bridge()
    report = "DEGRADED: 1 issues\n[Notes]\n  carla not reachable; no Carla state saved"

    async def degraded_save(name, d, ops):
        d.mkdir(parents=True, exist_ok=True)
        write_session(RigSession(name=name, graph=RigGraph(), looper_session_dir="looper"), d)
        return report

    with patch("carla_mcp.bridge.tools.sessions.do_save", new=degraded_save):
        out = asyncio.run(_tools(b)["session_save"].fn("tues"))
    assert out["ok"] is True and out["result"]["report"] == report
    assert b.session_name == "tues" and b.graph is not None


# ----- FAILED loads are errors and leave the bridge graph unchanged ---------

EMPTY_OBS = ObservedState(links=[], output_ports=[], input_ports=[], unit_status={})


def _prior_graph(b):
    g = RigGraph()
    b.graph, b.session_name = g, "earlier"
    return g


def test_failed_load_is_degraded_error_and_leaves_bridge_graph_unchanged():
    b = _bridge()
    _seed(b, "tues")  # a readable session: only the FAILED report keeps the graph out
    prior = _prior_graph(b)
    with patch("carla_mcp.bridge.tools.sessions.do_load",
               new=AsyncMock(return_value="FAILED: boom")) as load, \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=EMPTY_OBS)):
        out = asyncio.run(_tools(b)["session_load"].fn("tues"))
    assert load.await_count == 1
    assert out["ok"] is False and out["error"] == {"type": "degraded", "message": "FAILED: boom"}
    assert out["notes"] == []
    assert b.graph is prior and b.session_name == "earlier"
    assert not b.lock.locked()


def test_failed_load_through_real_do_load_on_a_dir_without_a_session_file():
    b = _bridge()
    (b.config.session_dir / "empty").mkdir(parents=True)
    prior = _prior_graph(b)
    out = asyncio.run(_tools(b)["session_load"].fn("empty"))
    assert out["ok"] is False and out["error"]["type"] == "degraded"
    assert out["error"]["message"].startswith("FAILED: No rig session found at ")
    assert b.graph is prior and b.session_name == "earlier"


def test_failed_multiline_load_report_is_kept_as_a_note():
    b = _bridge()
    _seed(b, "tues")
    report = "FAILED: boom\n[Notes]\n  detail"
    with patch("carla_mcp.bridge.tools.sessions.do_load", new=AsyncMock(return_value=report)):
        out = asyncio.run(_tools(b)["session_load"].fn("tues"))
    assert out["error"] == {"type": "degraded", "message": "FAILED: boom"}
    assert out["notes"] == [report]


def test_degraded_load_sets_graph_and_returns_the_report():
    b = _bridge()
    _seed(b, "tues")
    prior = _prior_graph(b)
    report = "DEGRADED: 1 issues\n[Issues]\n  down unit: carla:main"
    with patch("carla_mcp.bridge.tools.sessions.do_load", new=AsyncMock(return_value=report)), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=EMPTY_OBS)):
        out = asyncio.run(_tools(b)["session_load"].fn("tues"))
    assert out["ok"] is True and out["result"]["report"] == report
    assert b.graph is not None and b.graph is not prior
    assert list(b.graph.runtime_units) == ["carla:main"] and b.session_name == "tues"


def test_cold_rig_up_with_a_failed_session_load_is_degraded_and_graph_unchanged():
    b = _bridge()
    _seed(b, "tues")
    prior = _prior_graph(b)
    with patch("carla_mcp.bridge.tools.lifecycle.units.start_a2j", return_value=None), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_carla_main", new=AsyncMock(return_value=None)), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_looper_engine", new=AsyncMock(return_value=None)), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.unit_probe", return_value=False), \
         patch("carla_mcp.bridge.units.carla_gui_running", return_value=False), \
         patch("carla_mcp.bridge.units.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.tools.sessions.do_load", new=AsyncMock(return_value="FAILED: boom")), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=EMPTY_OBS)):
        out = asyncio.run(_lifecycle_tools(b)["rig_up"].fn(session="tues"))
    assert out["ok"] is False and out["error"] == {"type": "degraded", "message": "FAILED: boom"}
    assert b.graph is prior and b.session_name == "earlier"
    assert not b.lock.locked()
