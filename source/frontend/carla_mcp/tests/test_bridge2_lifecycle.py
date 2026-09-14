import asyncio
from unittest.mock import AsyncMock, patch

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.tools import lifecycle
from carla_mcp.rig.graph import RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, ObservedState
from carla_mcp.rig.reconcile import UNIT_START_ORDER
from carla_mcp.rig.session import RigSession, write_session


def _tools(b):
    return {t.name: t for t in lifecycle.build(b)}


def _bridge():
    b = Bridge.for_tests()
    b.looper.loopers = AsyncMock(return_value=[{"id": 1, "name": "uke", "port_index": 0, "mode": "Playing",
                                                "level_db": -1.0, "pan": 0.0, "input_source": None}])
    b.carla.version = AsyncMock(return_value={"worker": "w1"})
    return b


def _observed(units=None, links=()):
    return ObservedState(links=[Link(s, d) for s, d in links], output_ports=[], input_ports=[],
                         unit_status=units or {})


def test_annotations_and_names():
    t = _tools(_bridge())
    assert set(t) == {"rig_up", "rig_down", "rig_state", "rig_reset_routing"}
    assert t["rig_down"].annotations == {"destructiveHint": True}
    assert t["rig_reset_routing"].annotations == {"destructiveHint": True}
    assert t["rig_state"].annotations == {"readOnlyHint": True}


def test_rig_state_without_session():
    b = _bridge()
    with patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=_observed())):
        out = asyncio.run(_tools(b)["rig_state"].fn())
    assert out["ok"] is True
    assert out["result"]["verdict"] == "OK (no session loaded)"
    assert out["result"]["versions"] == {"bridge": "test", "carla": "w1"}
    assert out["result"]["loops"][0]["name"] == "uke"


def test_rig_state_compare_reads_named_session(tmp_path):
    b = _bridge()
    g = RigGraph()
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    sdir = b.config.session_dir / "tues"
    sdir.mkdir(parents=True)
    write_session(RigSession(name="tues", graph=g), sdir)
    with patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe",
               new=AsyncMock(return_value=_observed({"carla:main": False}))):
        out = asyncio.run(_tools(b)["rig_state"].fn(compare="tues"))
    assert out["result"]["verdict"].startswith("DEGRADED")
    missing = asyncio.run(_tools(b)["rig_state"].fn(compare="nope"))
    assert missing["ok"] is False and missing["error"]["type"] == "not_found"


def test_rig_state_rejects_bad_detail():
    b = _bridge()
    with patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=_observed())):
        out = asyncio.run(_tools(b)["rig_state"].fn(detail="xxl"))
    assert out["ok"] is False and out["error"]["type"] == "validation"


def test_rig_up_starts_units_in_order_and_returns_state():
    b = _bridge()
    order = []

    async def _start(name):
        order.append(name)
        return None if name != "looper" else "looper:engine not ready after 10s"

    def _start_a2j(b):  # start_a2j is synchronous in production
        order.append("a2j")
        return None

    async def _start_carla(b):
        return await _start("carla")

    async def _start_looper(b):
        return await _start("looper")

    with patch("carla_mcp.bridge.tools.lifecycle.units.start_a2j", side_effect=_start_a2j), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_carla_main", new=AsyncMock(side_effect=_start_carla)), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_looper_engine", new=AsyncMock(side_effect=_start_looper)), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=_observed())):
        out = asyncio.run(_tools(b)["rig_up"].fn())
    # Start order matches UNIT_START_ORDER: looper-engine (0) < a2j (2) < carla-main (3)
    assert order == ["looper", "a2j", "carla"]
    assert out["ok"] is True and out["result"]["started"] == ["a2j", "carla:main"]
    assert out["notes"] == ["looper:engine not ready after 10s"]
    assert "verdict" in out["result"]["state"]
    # Verify order is derived from UNIT_START_ORDER, not hardcoded: the kinds with starters sorted ascending.
    expected_order_kinds = sorted(
        ["looper-engine", "a2j", "carla-main"],
        key=lambda k: UNIT_START_ORDER[k]
    )
    assert expected_order_kinds == ["looper-engine", "a2j", "carla-main"]


def test_rig_down_clears_graph_and_reports():
    b = _bridge()
    b.graph = RigGraph(); b.session_name = "x"
    with patch("carla_mcp.bridge.tools.lifecycle.do_stop", new=AsyncMock(return_value="OK\n\nStopped: ...")) as stop:
        out = asyncio.run(_tools(b)["rig_down"].fn())
    assert out["result"]["report"].startswith("OK") and b.graph is None and b.session_name is None
    stop.assert_awaited_once()


def test_rig_reset_routing_dry_run_lists_links():
    b = _bridge()
    obs = _observed(links=[("loopers:loop0_out_l", "Carla:audio-in3"), ("alsa:a", "alsa:b")])
    with patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=obs)):
        out = asyncio.run(_tools(b)["rig_reset_routing"].fn(dry_run=True))
    assert out["result"] == {"dry_run": True,
                             "would_disconnect": [{"src": "loopers:loop0_out_l", "dst": "Carla:audio-in3"}]}
    with patch("carla_mcp.bridge.tools.lifecycle.do_routing_reset", new=AsyncMock(return_value="OK")) as reset:
        out = asyncio.run(_tools(b)["rig_reset_routing"].fn())
    assert out["result"] == {"dry_run": False, "report": "OK"} and reset.await_count == 1
