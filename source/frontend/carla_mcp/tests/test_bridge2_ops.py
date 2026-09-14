import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from carla_mcp.backends.rpc import RpcError
from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.ops import BridgeOps
from carla_mcp.rig.graph import RigGraph, RuntimeUnit


def _bridge(**kw):
    b = Bridge.for_tests(**kw)
    b.carla.project_load = AsyncMock(return_value={"path": "p"})
    b.carla.project_save = AsyncMock(return_value={"path": "p"})
    b.carla.handles = AsyncMock(return_value={"strat/comp": 1})
    b.looper.get_state = AsyncMock(return_value={"main_muted": True, "loopers": []})
    b.looper.load_session = AsyncMock(return_value={"ok": True})
    b.looper.save_session_at = AsyncMock(return_value={"ok": True})
    b.looper.set_main_mute = AsyncMock(return_value={"ok": True})
    b.looper.set_all_mute = AsyncMock(return_value={"ok": True})
    return b


def _graph():
    g = RigGraph()
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    g.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
    g.add_runtime_unit(RuntimeUnit(name="looper:mcp", kind="looper-mcp"))
    g.add_runtime_unit(RuntimeUnit(name="a2j", kind="a2j"))
    g.add_runtime_unit(RuntimeUnit(name="carla:strat", kind="carla-child", node="strat"))
    return g


def test_observe_probes_units_links_and_looper_state():
    b = _bridge()
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.ops.pw_link.list_links", return_value=[("loopers:loop0_out_l", "Carla:audio-in3")]), \
         patch("carla_mcp.bridge.ops.pw_link.list_outputs", return_value=["loopers:loop0_out_l"]), \
         patch("carla_mcp.bridge.ops.pw_link.list_inputs", return_value=["Carla:audio-in3", "CarlaChain_strat:audio-in1"]), \
         patch("carla_mcp.bridge.ops.tcp_reachable", side_effect=lambda h, p, **k: p == b.config.carla_rpc_port), \
         patch("carla_mcp.bridge.ops.a2j_running", return_value=False):
        observed = asyncio.run(ops.observe(_graph()))
    assert observed.unit_status == {"carla:main": True, "looper:engine": True, "looper:mcp": False,
                                    "a2j": False, "carla:strat": True}
    assert (observed.links[0].src, observed.links[0].dst) == ("loopers:loop0_out_l", "Carla:audio-in3")
    assert observed.looper_state["main_muted"] is True


def test_carla_project_and_looper_payload_translate_errors_to_strings():
    b = _bridge()
    ops = BridgeOps(b)
    assert asyncio.run(ops.load_carla_project("/p.carxp")) is None
    b.carla.project_load = AsyncMock(side_effect=RpcError("backend_unavailable", "down"))
    assert "down" in asyncio.run(ops.load_carla_project("/p.carxp"))
    assert asyncio.run(ops.set_looper_mutes(True, False)) is None
    b.looper.set_main_mute = AsyncMock(side_effect=RpcError("internal", "nope"))
    assert "nope" in asyncio.run(ops.set_looper_mutes(True, False))


def test_export_import_go_through_legacy_sse_shim():
    calls = []

    async def fake_sse(url, name, args):
        calls.append((name, args))
        return {"nodes": []} if name == "export_rig_state" else {"messages": ["m"]}

    b = _bridge(legacy_sse=fake_sse)
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=True):
        assert asyncio.run(ops.export_rig_state("/chains")) == {"nodes": []}
        assert asyncio.run(ops.import_rig_state({"nodes": []}, "/chains")) == {"messages": ["m"]}
    assert calls[0] == ("export_rig_state", {"chains_dir": "/chains"})
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False):
        assert asyncio.run(ops.export_rig_state("/chains")) is None


def test_start_and_stop_dispatch_by_kind():
    b = _bridge()
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.units.start_carla_main", new=AsyncMock(return_value=None)) as sc, \
         patch("carla_mcp.bridge.units.start_looper_engine", new=AsyncMock(return_value="boom")) as sl, \
         patch("carla_mcp.bridge.units.stop_a2j", return_value=None) as sa:
        assert asyncio.run(ops.start_unit(RuntimeUnit(name="carla:main", kind="carla-main"))) is None
        assert asyncio.run(ops.start_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))) == "boom"
        assert asyncio.run(ops.stop_unit(RuntimeUnit(name="a2j", kind="a2j"))) is None
    sc.assert_awaited_once_with(b); sl.assert_awaited_once_with(b); sa.assert_called_once_with(b)
    assert "unknown" in asyncio.run(ops.start_unit(RuntimeUnit(name="z", kind="zeppelin")))


def test_connect_disconnect_wait_ports():
    ops = BridgeOps(_bridge())
    with patch("carla_mcp.bridge.ops.pw_link.connect", return_value=None) as c, \
         patch("carla_mcp.bridge.ops.pw_link.disconnect", return_value="gone") as d, \
         patch("carla_mcp.bridge.ops.pw_link.list_outputs", return_value=["a:1"]), \
         patch("carla_mcp.bridge.ops.pw_link.list_inputs", return_value=[]):
        assert ops.connect("a:1", "b:1") is None and ops.disconnect("a:1", "b:1") == "gone"
        assert ops.wait_ports(["a:1", "zz:9"], timeout_s=0.01) == ["zz:9"]
