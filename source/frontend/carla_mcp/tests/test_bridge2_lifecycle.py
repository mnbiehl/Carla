import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from carla_mcp.backends.rpc import RpcError
from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.result import ToolError
from carla_mcp.bridge.tools import lifecycle
from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, ObservedState
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
         patch.object(b.processes, "is_running", side_effect=lambda name: name in order_owned(order)), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=_observed())):
        out = asyncio.run(_tools(b)["rig_up"].fn())
    # Start order matches UNIT_START_ORDER: looper-engine (0) < a2j (2) < carla-main (3)
    assert order == ["looper", "a2j", "carla"]
    assert out["ok"] is True and out["result"]["started"] == ["a2j", "carla:main"]
    assert out["result"]["already_up"] == []
    assert out["notes"] == ["looper:engine not ready after 10s"]
    assert "verdict" in out["result"]["state"]


def order_owned(order):
    """Units the fake ProcessManager 'owns': those whose starter has run."""
    return {{"looper": "looper:engine", "a2j": "a2j", "carla": "carla:main"}[n] for n in order}


def _owned_after_start(names):
    """is_running side effect: a unit in `names` reads as owned from its second
    probe on (its starter spawned it in between); any other unit never does."""
    seen = {}

    def probe(name):
        seen[name] = seen.get(name, 0) + 1
        return name in names and seen[name] >= 2
    return probe


def test_rig_up_reports_adopted_units_as_already_up_not_started():
    """A starter succeeds both when it spawned the unit and when it found one
    running. Only units the ProcessManager owns afterwards count as started."""
    b = _bridge()
    with patch("carla_mcp.bridge.tools.lifecycle.units.start_a2j", return_value=None), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_carla_main", new=AsyncMock(return_value=None)), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_looper_engine", new=AsyncMock(return_value=None)), \
         patch.object(b.processes, "is_running", side_effect=lambda name: name == "a2j"), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=_observed())):
        out = asyncio.run(_tools(b)["rig_up"].fn())
    assert out["ok"] is True
    # a2j was "owned" before its starter ran (a repeat rig_up), so it is not newly started.
    assert out["result"]["started"] == []
    assert out["result"]["already_up"] == ["looper:engine", "a2j", "carla:main"]


def test_rig_down_clears_graph_and_reports():
    b = _bridge()
    b.graph = RigGraph(); b.session_name = "x"
    with patch("carla_mcp.bridge.tools.lifecycle.do_stop", new=AsyncMock(return_value="OK\n\nStopped: ...")) as stop:
        out = asyncio.run(_tools(b)["rig_down"].fn())
    assert out["result"]["report"].startswith("OK") and b.graph is None and b.session_name is None
    stop.assert_awaited_once()


def test_rig_down_keeps_graph_when_stop_is_degraded():
    b = _bridge()
    g = RigGraph(); b.graph = g; b.session_name = "x"
    report = "DEGRADED: 2 issues\n\nIssues:\n  - stop carla:main: not started by this bridge; left running"
    with patch("carla_mcp.bridge.tools.lifecycle.do_stop", new=AsyncMock(return_value=report)):
        out = asyncio.run(_tools(b)["rig_down"].fn())
    assert out["ok"] is True and out["result"]["report"] == report
    assert b.graph is g and b.session_name == "x"


def test_rig_down_after_bridge_restart_reports_adopted_units_and_keeps_graph():
    """Real do_stop + BridgeOps: nothing was spawned by this bridge, the rig is up."""
    b = _bridge()
    g = RigGraph()
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    g.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
    b.graph = g; b.session_name = "tues"
    b.looper.get_state = AsyncMock(return_value={"loopers": []})
    with patch("carla_mcp.bridge.units.tcp_reachable", return_value=True), \
         patch("carla_mcp.bridge.ops.tcp_reachable", return_value=True), \
         patch("carla_mcp.backends.pw_link.list_outputs", return_value=["loopers:loop0_out_l"]), \
         patch("carla_mcp.backends.pw_link.list_inputs", return_value=[]), \
         patch("carla_mcp.backends.pw_link.list_links", return_value=[]), \
         patch.object(b.processes, "stop", wraps=b.processes.stop) as stop:
        out = asyncio.run(_tools(b)["rig_down"].fn())
    report = out["result"]["report"]
    assert report.startswith("DEGRADED")
    assert "[Stopped]" not in report  # adopted units are issues, never listed as stopped
    assert "stop carla:main: not started by this bridge; left running" in report
    assert "stop looper:engine: not started by this bridge; left running" in report
    assert stop.call_count == 2
    assert b.graph is g and b.session_name == "tues"


def test_rig_down_with_units_already_down_is_ok_and_clears_graph():
    b = _bridge()
    g = RigGraph()
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    b.graph = g; b.session_name = "tues"
    with patch("carla_mcp.bridge.units.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False), \
         patch("carla_mcp.backends.pw_link.list_outputs", return_value=[]), \
         patch("carla_mcp.backends.pw_link.list_inputs", return_value=[]), \
         patch("carla_mcp.backends.pw_link.list_links", return_value=[]):
        out = asyncio.run(_tools(b)["rig_down"].fn())
    assert out["result"]["report"].startswith("OK"), out
    assert b.graph is None and b.session_name is None


# ----- rig_reset_routing: rewire to the loaded session (links only) -----------

MON0 = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"
MON1 = "alsa_output.usb-F-00.pro-output-0:playback_AUX1"
STRAY = ("loopers:loop1_out_l", "Carla:audio-in3")
DESKTOP = ("Firefox:output_FL", MON0)
KEPT = ("loopers:loop0_out_l", "Carla:audio-in1")
MISSING = [("loopers:loop0_out_r", "Carla:audio-in2")]


class FakePipeWire:
    OUTPUTS = ["loopers:loop0_out_l", "loopers:loop0_out_r", "loopers:loop1_out_l", "Firefox:output_FL"]
    INPUTS = ["Carla:audio-in1", "Carla:audio-in2", "Carla:audio-in3", MON0, MON1]

    def __init__(self, links):
        self.links = set(links)
        self.connected, self.disconnected = [], []

    def list_links(self):
        return sorted(self.links)

    def list_outputs(self):
        return list(self.OUTPUTS)

    def list_inputs(self):
        return list(self.INPUTS)

    def connect(self, src, dst):
        self.links.add((src, dst)); self.connected.append((src, dst))

    def disconnect(self, src, dst):
        self.links.discard((src, dst)); self.disconnected.append((src, dst))


def _session_graph():
    """loop:0 -> Carla main (explicit ports), plus a2j as a runtime unit."""
    g = RigGraph()
    g.add_node(Node(name="loop:0", kind="loop", port_index=0))
    g.add_node(Node(name="Carla", kind="endpoint", jack_client="Carla:audio-in"))
    g.add_edge("loop:0", "Carla", src_port="loopers:loop0_out_l", dst_port="Carla:audio-in1")
    g.add_edge("loop:0", "Carla", src_port="loopers:loop0_out_r", dst_port="Carla:audio-in2")
    g.add_runtime_unit(RuntimeUnit(name="a2j", kind="a2j"))
    return g


def _rewire(b, pw, **kwargs):
    """Run rig_reset_routing through the real do_rewire + BridgeOps over a fake
    PipeWire; every process, Carla and looper side effect is a tripwire."""
    forbidden = AsyncMock(side_effect=AssertionError("rig_reset_routing must only change links"))
    tripwires = {
        name: patch(f"carla_mcp.bridge.ops.BridgeOps.{name}", new=forbidden)
        for name in ("start_unit", "stop_unit", "load_carla_project", "import_rig_state",
                     "load_looper_session", "set_looper_mutes", "looper_save_session_at")
    }
    b.looper.get_state = AsyncMock(return_value={"loopers": []})
    with patch("carla_mcp.backends.pw_link.list_links", side_effect=pw.list_links), \
         patch("carla_mcp.backends.pw_link.list_outputs", side_effect=pw.list_outputs), \
         patch("carla_mcp.backends.pw_link.list_inputs", side_effect=pw.list_inputs), \
         patch("carla_mcp.backends.pw_link.connect", side_effect=pw.connect), \
         patch("carla_mcp.backends.pw_link.disconnect", side_effect=pw.disconnect), \
         patch("carla_mcp.bridge.ops.BridgeOps.wait_ports", side_effect=AssertionError("no waits")), \
         patch("carla_mcp.bridge.ops.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.ops.a2j_running", return_value=False), \
         patch.object(b.processes, "spawn", side_effect=AssertionError("no spawn")), \
         patch.object(b.processes, "stop", side_effect=AssertionError("no stop")), \
         tripwires["start_unit"], tripwires["stop_unit"], tripwires["load_carla_project"], \
         tripwires["import_rig_state"], tripwires["load_looper_session"], \
         tripwires["set_looper_mutes"], tripwires["looper_save_session_at"]:
        out = asyncio.run(_tools(b)["rig_reset_routing"].fn(**kwargs))
    assert forbidden.await_count == 0
    return out


def test_rig_reset_routing_without_session_is_validation_and_touches_nothing():
    b = _bridge()
    with patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock()) as observe:
        for dry_run in (True, False):
            out = asyncio.run(_tools(b)["rig_reset_routing"].fn(dry_run=dry_run))
            assert out["ok"] is False and out["error"] == {
                "type": "validation", "message": lifecycle.NO_SESSION_TO_RESET_MESSAGE}
            assert out["error"]["message"] == \
                "no session loaded; nothing to reset routing to (use session_load)"
    observe.assert_not_awaited()
    assert not b.lock.locked()


def test_rig_reset_routing_dry_run_lists_planned_disconnects_and_connects_only():
    b = _bridge()
    b.graph = _session_graph()
    pw = FakePipeWire({KEPT, STRAY, DESKTOP})
    out = _rewire(b, pw, dry_run=True)
    assert out["ok"] is True, out
    assert out["result"] == {
        "dry_run": True,
        "would_disconnect": [{"src": STRAY[0], "dst": STRAY[1]}],
        "would_connect": [{"src": s, "dst": d} for s, d in MISSING],
        "not_fixable_by_rewiring": ["down unit: a2j"],
    }
    assert pw.connected == [] and pw.disconnected == []
    assert pw.links == {KEPT, STRAY, DESKTOP}


def test_rig_reset_routing_rewires_to_the_loaded_session_and_changes_nothing_else():
    b = _bridge()
    g = _session_graph()
    b.graph = g; b.session_name = "tues"
    pw = FakePipeWire({KEPT, STRAY, DESKTOP})
    out = _rewire(b, pw)
    assert out["ok"] is True, out
    assert pw.disconnected == [STRAY]
    assert pw.connected == MISSING
    assert pw.links == {KEPT, DESKTOP, *MISSING}    # desktop link left alone
    res = out["result"]
    assert res["dry_run"] is False
    assert res["disconnected"] == [{"src": STRAY[0], "dst": STRAY[1]}]
    assert res["connected"] == [{"src": s, "dst": d} for s, d in MISSING]
    # Rewiring cannot start a2j: reported, never fixed.
    assert res["verdict"] == "DEGRADED: 1 issues"
    assert res["report"].splitlines()[0] == "DEGRADED: 1 issues"
    assert "down unit: a2j" in res["report"]
    assert out["notes"] == []
    assert b.graph is g and b.session_name == "tues" and not b.lock.locked()


def test_rig_reset_routing_connect_failure_is_a_note():
    b = _bridge()
    b.graph = _session_graph()
    pw = FakePipeWire({KEPT})
    pw.connect = lambda src, dst: "device busy"
    out = _rewire(b, pw)
    assert out["ok"] is True
    assert out["notes"] == [f"connect {MISSING[0][0]} -> {MISSING[0][1]}: device busy"]
    assert out["result"]["connected"] == []
    assert out["result"]["verdict"] == "DEGRADED: 2 issues"


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


def _run_rig_up(b, up_kinds, carla_without_worker=None, looper_tcp_reachable=False, **kwargs):
    """`carla_without_worker`: None, or "pgrep"/"sse" for which probe of
    units.carla_running_without_worker reports a Carla lacking the RPC worker.
    `looper_tcp_reachable`: the looper's own TCP-port probe (lifecycle.tcp_reachable),
    independent of the pw-link-based unit_probe."""
    calls = []
    a2j, carla, looper = _starter_patches(calls)
    load = AsyncMock(return_value=["OK\n"])
    probe = patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.unit_probe",
                  side_effect=lambda self, unit: unit.kind in up_kinds, autospec=True)
    with a2j, carla, looper, probe as unit_probe, \
         patch("carla_mcp.bridge.units.carla_gui_running", return_value=carla_without_worker == "pgrep"), \
         patch("carla_mcp.bridge.units.tcp_reachable", return_value=carla_without_worker == "sse"), \
         patch("carla_mcp.bridge.tools.lifecycle.tcp_reachable", return_value=looper_tcp_reachable), \
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


@pytest.mark.parametrize("via", ["pgrep", "sse"])
def test_rig_up_with_session_refuses_when_carla_runs_without_the_rpc_worker(via):
    # RPC 8089 and the looper probe both say down, but a Carla GUI without the
    # worker is running: a session load would clear its rig-space links.
    out, calls, load, _ = _run_rig_up(_bridge(), set(), carla_without_worker=via, session="tues")
    assert out["ok"] is False
    assert out["error"] == {"type": "validation", "message": lifecycle.RIG_ALREADY_UP_MESSAGE}
    assert out["notes"] == ["up: carla:main (running without the RPC worker)"]
    assert calls == [] and load.await_count == 0


def test_rig_up_with_session_refuses_when_looper_tcp_reachable_despite_empty_pwlink_ports():
    # The pw-link-based unit_probe reads the looper as down (as it would if
    # `pw-link -o` failed or timed out), but the looper's own TCP port still
    # answers: rig_up(session=) must still refuse rather than load over it.
    out, calls, load, _ = _run_rig_up(_bridge(), set(), looper_tcp_reachable=True, session="tues")
    assert out["ok"] is False and out["error"]["type"] == "validation"
    assert out["error"]["message"] == lifecycle.RIG_ALREADY_UP_MESSAGE
    assert any(note.startswith("up: looper:engine") for note in out["notes"])
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


def test_rig_up_failed_cold_load_reports_started_units_in_the_error_notes():
    """Units are already started by the time a cold load FAILs; that context
    must not be dropped when the ToolError crosses the tool boundary."""
    b = _bridge()
    started_by_bridge = {"looper:engine", "carla:main"}  # a2j was already running
    load = AsyncMock(side_effect=ToolError("degraded", "FAILED: boom"))
    with patch("carla_mcp.bridge.tools.sessions.load_session_into", new=load), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_a2j", return_value=None), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_carla_main",
               new=AsyncMock(return_value=None)), \
         patch("carla_mcp.bridge.tools.lifecycle.units.start_looper_engine",
               new=AsyncMock(return_value=None)), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.unit_probe", return_value=False), \
         patch("carla_mcp.bridge.units.carla_gui_running", return_value=False), \
         patch("carla_mcp.bridge.units.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.tools.lifecycle.tcp_reachable", return_value=False), \
         patch.object(b.processes, "is_running", side_effect=_owned_after_start(started_by_bridge)), \
         patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=_observed())):
        out = asyncio.run(_tools(b)["rig_up"].fn(session="tues"))
    assert out["ok"] is False
    assert out["error"] == {"type": "degraded", "message": "FAILED: boom"}
    assert out["notes"] == ["started: looper:engine, carla:main", "already up: a2j"]
