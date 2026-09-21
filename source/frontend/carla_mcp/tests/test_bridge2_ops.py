import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from carla_mcp.backends.legacy_sse import LEGACY_SSE_LONG_TIMEOUT_S
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


def test_observe_without_graph_probes_core_units():
    b = _bridge()
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.ops.pw_link.list_links", return_value=[]), \
         patch("carla_mcp.bridge.ops.pw_link.list_outputs", return_value=["loopers:loop0_out_l"]), \
         patch("carla_mcp.bridge.ops.pw_link.list_inputs", return_value=[]), \
         patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.ops.a2j_running", return_value=True):
        observed = asyncio.run(ops.observe(None))
    assert observed.unit_status == {"looper:engine": True, "a2j": True, "carla:main": False}


def test_observe_never_raises_when_a_probe_or_listing_fails():
    """A probe that blows up (fork EAGAIN, undecodable port name) reads as
    down/empty; observation must not abort rig_state or a converge."""
    b = _bridge()
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.ops.pw_link.list_links", side_effect=OSError("EAGAIN")), \
         patch("carla_mcp.bridge.ops.pw_link.list_outputs", return_value=["loopers:loop0_out_l"]), \
         patch("carla_mcp.bridge.ops.pw_link.list_inputs", side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")), \
         patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.ops.a2j_running", side_effect=PermissionError("nope")):
        observed = asyncio.run(ops.observe(None))
    assert observed.links == []
    assert observed.unit_status == {"looper:engine": True, "a2j": False, "carla:main": False}


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

    async def fake_sse(url, name, args, timeout=None):
        calls.append((name, args, timeout))
        return {"nodes": []} if name == "export_rig_state" else {"messages": ["m"]}

    b = _bridge(legacy_sse=fake_sse)
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=True):
        assert asyncio.run(ops.export_rig_state("/chains")) == {"nodes": []}
        assert asyncio.run(ops.import_rig_state({"nodes": []}, "/chains")) == {"messages": ["m"]}
    assert calls[0] == ("export_rig_state", {"chains_dir": "/chains"}, LEGACY_SSE_LONG_TIMEOUT_S)
    assert calls[1] == (
        "import_rig_state", {"state": {"nodes": []}, "chains_dir": "/chains"}, LEGACY_SSE_LONG_TIMEOUT_S
    )
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False):
        assert asyncio.run(ops.export_rig_state("/chains")) is None


def test_export_import_translate_rpc_error_from_legacy_sse():
    b = _bridge(legacy_sse=AsyncMock(side_effect=RpcError("internal", "import_rig_state: boom")))
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=True):
        result = asyncio.run(ops.import_rig_state({"nodes": []}, "/chains"))
        assert result["messages"] and "boom" in result["messages"][0]
        # Carla was reachable but the call itself failed: the real message
        # comes back (not silently collapsed to None / "carla not reachable").
        export = asyncio.run(ops.export_rig_state("/chains"))
        assert export is not None and "nodes" not in export
        assert "boom" in export["error"]


def test_export_returns_none_only_when_carla_actually_unreachable():
    b = _bridge(legacy_sse=AsyncMock(side_effect=RpcError("internal", "should not be called")))
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False):
        assert asyncio.run(ops.export_rig_state("/chains")) is None


def test_rig_handles_and_remove_node_use_default_timeout():
    calls = []

    async def fake_sse(url, name, args, timeout=None):
        calls.append((name, timeout))
        return {"success": True} if name == "remove_node" else {"nodes": {}}

    b = _bridge(legacy_sse=fake_sse)
    ops = BridgeOps(b)
    # observe()/unit_probe() go through pw_link + a2j_running for real
    # (pw-link -o/-i/-l, pgrep -x a2jmidid) unless mocked; this rig-isolation
    # guard would (rightly) trip on that, so mock them all here like the
    # other BridgeOps.observe tests in this file do.
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=True), \
         patch("carla_mcp.bridge.ops.pw_link.list_links", return_value=[]), \
         patch("carla_mcp.bridge.ops.pw_link.list_outputs", return_value=[]), \
         patch("carla_mcp.bridge.ops.pw_link.list_inputs", return_value=[]), \
         patch("carla_mcp.bridge.ops.a2j_running", return_value=False):
        asyncio.run(ops.observe(_graph()))
        unit = RuntimeUnit(name="carla:strat", kind="carla-child", node="strat")
        asyncio.run(ops.stop_unit(unit))
    names = dict(calls)
    assert names["rig_handles"] is None
    assert names["remove_node"] is None


def test_start_and_stop_dispatch_by_kind():
    b = _bridge()
    ops = BridgeOps(b)
    with patch("carla_mcp.bridge.units.start_carla_main", new=AsyncMock(return_value=None)) as sc, \
         patch("carla_mcp.bridge.units.start_looper_engine", new=AsyncMock(return_value="boom")) as sl, \
         patch("carla_mcp.bridge.units.stop_a2j", new=AsyncMock(return_value=None)) as sa, \
         patch("carla_mcp.bridge.units.start_a2j", return_value="no a2j") as st_a2j:
        assert asyncio.run(ops.start_unit(RuntimeUnit(name="carla:main", kind="carla-main"))) is None
        assert asyncio.run(ops.start_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))) == "boom"
        assert asyncio.run(ops.start_unit(RuntimeUnit(name="a2j", kind="a2j"))) == "no a2j"
        assert asyncio.run(ops.stop_unit(RuntimeUnit(name="a2j", kind="a2j"))) is None
    sc.assert_awaited_once_with(b); sl.assert_awaited_once_with(b); sa.assert_awaited_once_with(b)
    st_a2j.assert_called_once_with(b)
    assert "unknown" in asyncio.run(ops.start_unit(RuntimeUnit(name="z", kind="zeppelin")))


def test_stop_unit_carla_child_reports_errors_not_success():
    b = _bridge()
    ops = BridgeOps(b)
    unit = RuntimeUnit(name="carla:strat", kind="carla-child", node="strat")

    # Carla down: must not silently succeed.
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False):
        err = asyncio.run(ops.stop_unit(unit))
    assert err is not None and "not reachable" in err

    # remove_node raises RpcError (e.g. legacy tool isError): surfaced as an error string.
    b.legacy_sse = AsyncMock(side_effect=RpcError("internal", "remove_node: node not found"))
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=True):
        err = asyncio.run(ops.stop_unit(unit))
    assert err is not None and "node not found" in err

    # remove_node returns success: false: surfaced as an error string, not success.
    b.legacy_sse = AsyncMock(return_value={"success": False, "message": "still connected"})
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=True):
        err = asyncio.run(ops.stop_unit(unit))
    assert err == "still connected"

    # remove_node succeeds: no error.
    b.legacy_sse = AsyncMock(return_value={"success": True})
    with patch("carla_mcp.bridge.ops.tcp_reachable", return_value=True):
        assert asyncio.run(ops.stop_unit(unit)) is None


def test_connect_disconnect_wait_ports():
    ops = BridgeOps(_bridge())
    with patch("carla_mcp.bridge.ops.pw_link.connect", return_value=None) as c, \
         patch("carla_mcp.bridge.ops.pw_link.disconnect", return_value="gone") as d, \
         patch("carla_mcp.bridge.ops.pw_link.list_outputs", return_value=["a:1"]), \
         patch("carla_mcp.bridge.ops.pw_link.list_inputs", return_value=[]):
        assert asyncio.run(ops.connect("a:1", "b:1")) is None
        assert asyncio.run(ops.disconnect("a:1", "b:1")) == "gone"
        assert asyncio.run(ops.wait_ports(["a:1", "zz:9"], timeout_s=0.01)) == ["zz:9"]
    c.assert_called_once_with("a:1", "b:1"); d.assert_called_once_with("a:1", "b:1")


def test_observe_and_wait_ports_keep_the_event_loop_free():
    """Blocking probes run off the loop: a concurrent coroutine must make
    progress while observe() and wait_ports() are inside a slow pw-link call."""
    import time

    ops = BridgeOps(_bridge())
    ticks = []

    async def ticker(stop):
        while not stop.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.005)

    def slow_list():
        time.sleep(0.08)
        return []

    async def scenario():
        stop = asyncio.Event()
        t = asyncio.ensure_future(ticker(stop))
        await ops.observe(None)
        await ops.wait_ports(["never:1"], timeout_s=0.1)
        stop.set()
        await t

    with patch("carla_mcp.bridge.ops.pw_link.list_links", side_effect=slow_list), \
         patch("carla_mcp.bridge.ops.pw_link.list_outputs", side_effect=slow_list), \
         patch("carla_mcp.bridge.ops.pw_link.list_inputs", side_effect=slow_list), \
         patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.ops.a2j_running", return_value=False):
        asyncio.run(scenario())
    # ~180 ms of blocking probes; a frozen loop would yield only a handful of ticks.
    assert len(ticks) > 10, len(ticks)
