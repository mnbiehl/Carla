import asyncio
from unittest.mock import AsyncMock, patch

from carla_mcp.backends.rpc import RpcError
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


CORE_UP = {"looper:engine": True, "a2j": True, "carla:main": True}


def test_rig_state_without_session():
    b = _bridge()
    with patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe",
               new=AsyncMock(return_value=_observed(dict(CORE_UP)))) as observe:
        out = asyncio.run(_tools(b)["rig_state"].fn())
    assert out["ok"] is True
    assert out["result"]["verdict"] == "OK (no session loaded)"
    assert out["result"]["units"] == {name: {"up": True} for name in CORE_UP}
    assert out["result"]["versions"] == {"bridge": "test", "carla": "w1"}
    assert out["result"]["loops"][0]["name"] == "uke"
    assert observe.await_args.args[0] is None


def test_rig_state_without_session_reports_down_core_units():
    b = _bridge()
    b.carla.version = AsyncMock(side_effect=RpcError("backend_unavailable", "down"))
    obs = _observed({"looper:engine": False, "a2j": True, "carla:main": False})
    with patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=obs)):
        out = asyncio.run(_tools(b)["rig_state"].fn())
    assert out["ok"] is True
    st = out["result"]
    assert st["verdict"] == "DEGRADED: 2 issues"
    assert st["issues"] == ["down unit: looper:engine", "down unit: carla:main"]
    assert st["units"]["carla:main"] == {"up": False} and st["versions"]["carla"] == "down"


def test_rig_state_without_session_probes_core_units_through_real_observe():
    b = _bridge()
    with patch("carla_mcp.bridge.ops.pw_link.list_links", return_value=[]), \
         patch("carla_mcp.bridge.ops.pw_link.list_outputs", return_value=[]), \
         patch("carla_mcp.bridge.ops.pw_link.list_inputs", return_value=[]), \
         patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.ops.a2j_running", return_value=False):
        out = asyncio.run(_tools(b)["rig_state"].fn())
    st = out["result"]
    assert st["verdict"] == "DEGRADED: 3 issues"
    assert st["units"] == {"looper:engine": {"up": False}, "a2j": {"up": False}, "carla:main": {"up": False}}


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


# ----- C1: rig_up(session=...) only loads onto a cold rig ---------------------

def _starter_patches(calls):
    def _a2j(b):
        calls.append("a2j")
        return None

    async def _carla(b):
        calls.append("carla")
        return None

    async def _looper(b):
        calls.append("looper")
        return None

    return (patch("carla_mcp.bridge.tools.lifecycle.units.start_a2j", side_effect=_a2j),
            patch("carla_mcp.bridge.tools.lifecycle.units.start_carla_main", new=AsyncMock(side_effect=_carla)),
            patch("carla_mcp.bridge.tools.lifecycle.units.start_looper_engine", new=AsyncMock(side_effect=_looper)))


def _run_rig_up(b, up_kinds, **kwargs):
    calls = []
    a2j, carla, looper = _starter_patches(calls)
    load = AsyncMock(return_value=["OK\n"])
    probe = patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.unit_probe",
                  side_effect=lambda self, unit: unit.kind in up_kinds, autospec=True)
    with a2j, carla, looper, probe as unit_probe, \
         patch("carla_mcp.bridge.tools.sessions.load_session_into", new=load), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=_observed())):
        out = asyncio.run(_tools(b)["rig_up"].fn(**kwargs))
    return out, calls, load, unit_probe


def test_rig_up_with_session_refuses_when_carla_already_up():
    out, calls, load, _ = _run_rig_up(_bridge(), {"carla-main"}, session="tues")
    assert out["ok"] is False and out["error"]["type"] == "validation"
    assert out["error"]["message"] == lifecycle.RIG_ALREADY_UP_MESSAGE
    assert out["notes"] == ["up: carla:main"]
    assert calls == [] and load.await_count == 0


def test_rig_up_with_session_refuses_when_looper_already_up():
    out, calls, load, _ = _run_rig_up(_bridge(), {"looper-engine"}, session="tues")
    assert out["ok"] is False and out["error"]["type"] == "validation"
    assert "session_load" in out["error"]["message"]
    assert calls == [] and load.await_count == 0


def test_rig_up_with_session_loads_on_cold_start():
    b = _bridge()
    out, calls, load, unit_probe = _run_rig_up(b, set(), session="tues")
    assert out["ok"] is True, out
    assert calls == ["looper", "a2j", "carla"]
    load.assert_awaited_once_with(b, "tues")
    assert "OK\n" in out["notes"]
    # The guard probed the core units before anything was started.
    assert sorted(c.args[1].name for c in unit_probe.call_args_list) == ["carla:main", "looper:engine"]


def test_rig_up_without_session_stays_idempotent_when_rig_is_up():
    out, calls, load, unit_probe = _run_rig_up(_bridge(), {"carla-main", "looper-engine"})
    assert out["ok"] is True
    assert calls == ["looper", "a2j", "carla"]  # starters adopt running units themselves
    assert load.await_count == 0 and unit_probe.call_count == 0
    assert _tools(_bridge())["rig_up"].annotations == {"idempotentHint": True}


def test_rig_up_state_is_degraded_after_a_failed_start():
    b = _bridge()
    calls = []
    a2j, carla, looper = _starter_patches(calls)
    obs = _observed({"looper:engine": True, "a2j": True, "carla:main": False})
    with a2j, looper, \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_carla_main",
               new=AsyncMock(return_value="carla:main spawn failed: no pw-jack")), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=obs)):
        out = asyncio.run(_tools(b)["rig_up"].fn())
    assert out["ok"] is True and out["notes"] == ["carla:main spawn failed: no pw-jack"]
    assert out["result"]["state"]["verdict"] == "DEGRADED: 1 issues"
    assert out["result"]["state"]["issues"] == ["down unit: carla:main"]
