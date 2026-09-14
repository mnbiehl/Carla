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
