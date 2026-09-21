import asyncio
from unittest.mock import patch

from carla_mcp.bridge import units
from carla_mcp.bridge.app import Bridge


def _b():
    return Bridge.for_tests()


def _sse_port(b):
    return units._sse_host_port(b)[1]


def test_start_carla_main_spawns_and_waits_for_rpc(monkeypatch):
    b = _b()
    monkeypatch.setattr(units, "POLL_S", 0.001)
    rpc_reach = iter([False, False, True])

    def reachable(host, port, **kw):
        return next(rpc_reach) if port == b.config.carla_rpc_port else False

    with patch("carla_mcp.bridge.units.tcp_reachable", side_effect=reachable), \
         patch("carla_mcp.bridge.units.carla_gui_running", return_value=False), \
         patch.object(b.processes, "spawn", return_value=77) as spawn, \
         patch.object(b.processes, "is_running", return_value=True):
        assert asyncio.run(units.start_carla_main(b)) is None
    spec = spawn.call_args.args[0]
    assert spec.argv == ["pw-jack", b.config.carla_python, str(b.config.frontend_dir / "carla.py")]
    assert spec.env["CARLA_RPC_PORT"] == str(b.config.carla_rpc_port)
    assert spec.name == "carla:main"


def test_start_carla_main_adopts_external_instance():
    b = _b()
    with patch("carla_mcp.bridge.units.tcp_reachable", return_value=True), \
         patch.object(b.processes, "spawn") as spawn:
        assert asyncio.run(units.start_carla_main(b)) is None
    spawn.assert_not_called()


def test_start_carla_main_reports_early_exit(monkeypatch):
    b = _b()
    monkeypatch.setattr(units, "POLL_S", 0.001)
    with patch("carla_mcp.bridge.units.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.units.carla_gui_running", return_value=False), \
         patch.object(b.processes, "spawn", return_value=1), \
         patch.object(b.processes, "is_running", return_value=False):
        msg = asyncio.run(units.start_carla_main(b))
    assert msg and "exited" in msg


def test_start_carla_main_refuses_second_instance_when_carla_py_running_without_worker():
    b = _b()
    with patch("carla_mcp.bridge.units.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.units.carla_gui_running", return_value=True), \
         patch.object(b.processes, "spawn") as spawn:
        msg = asyncio.run(units.start_carla_main(b))
    spawn.assert_not_called()
    assert msg == (f"Carla is running without the RPC worker on {b.config.carla_rpc_port}; "
                   "not starting a second instance (restart Carla from this branch)")


def test_start_carla_main_refuses_second_instance_when_legacy_sse_port_answers():
    b = Bridge.for_tests(env={"CARLA_MCP_PORT": "3"})  # distinct from the closed RPC port 1
    probed = []

    def reachable(host, port, **kw):
        probed.append(port)
        return port == _sse_port(b)

    with patch("carla_mcp.bridge.units.tcp_reachable", side_effect=reachable), \
         patch("carla_mcp.bridge.units.carla_gui_running", return_value=False), \
         patch.object(b.processes, "spawn") as spawn:
        msg = asyncio.run(units.start_carla_main(b))
    spawn.assert_not_called()
    assert msg is not None and "without the RPC worker" in msg
    assert probed == [b.config.carla_rpc_port, _sse_port(b)]


def test_start_carla_main_spawn_oserror_is_returned_not_raised():
    b = _b()
    with patch("carla_mcp.bridge.units.tcp_reachable", return_value=False), \
         patch("carla_mcp.bridge.units.carla_gui_running", return_value=False), \
         patch.object(b.processes, "spawn", side_effect=FileNotFoundError("pw-jack")):
        msg = asyncio.run(units.start_carla_main(b))
    assert msg is not None and msg.startswith("carla:main spawn failed:") and "pw-jack" in msg


def test_start_looper_engine_spawn_oserror_is_returned_not_raised():
    b = _b()
    with patch("carla_mcp.bridge.units.pw_link.list_outputs", return_value=[]), \
         patch.object(b.processes, "spawn", side_effect=PermissionError("denied")):
        msg = asyncio.run(units.start_looper_engine(b))
    assert msg is not None and msg.startswith("looper:engine spawn failed:") and "denied" in msg


def test_start_a2j_spawn_oserror_is_returned_not_raised():
    b = _b()
    with patch("carla_mcp.bridge.units.a2j_running", return_value=False), \
         patch.object(b.processes, "spawn", side_effect=PermissionError("denied")):
        assert units.start_a2j(b) == "a2j spawn failed: denied"


def test_start_looper_engine_waits_for_ports(monkeypatch):
    b = _b()
    monkeypatch.setattr(units, "POLL_S", 0.001)
    outs = iter([[], [], ["loopers:loop0_out_l"]])
    with patch("carla_mcp.bridge.units.pw_link.list_outputs", side_effect=lambda: next(outs)), \
         patch.object(b.processes, "spawn", return_value=5) as spawn, \
         patch.object(b.processes, "is_running", return_value=True):
        assert asyncio.run(units.start_looper_engine(b)) is None
    assert spawn.call_args.args[0].argv == ["pw-jack", b.config.loopers_path, "--managed",
                                            "--remote-json-port", str(b.config.looper_port)]


def _stop_all(b):
    return [asyncio.run(units.stop_carla_main(b)), asyncio.run(units.stop_looper_engine(b)),
            asyncio.run(units.stop_a2j(b))]


def test_wait_deadline_counts_probe_time_not_just_sleeps(monkeypatch):
    """Each readiness probe can take as long as a TCP connect timeout; the
    deadline is wall clock, so slow probes cannot stretch a 20 s wait to 30 s."""
    import time
    monkeypatch.setattr(units, "POLL_S", 0.001)

    def slow_probe():
        time.sleep(0.02)
        return False

    t0 = time.monotonic()
    msg = asyncio.run(units._wait(slow_probe, 0.05, lambda: True))
    elapsed = time.monotonic() - t0
    assert msg == "not ready after 0s"
    assert elapsed < 0.2, elapsed


def test_wait_returns_ready_before_checking_the_deadline():
    calls = iter([False, True])
    assert asyncio.run(units._wait(lambda: next(calls), 10.0, lambda: True)) is None


def _probes(up):
    return (patch("carla_mcp.bridge.units.tcp_reachable", return_value=up),
            patch("carla_mcp.bridge.units.pw_link.list_outputs",
                  return_value=["loopers:loop0_out_l"] if up else []),
            patch("carla_mcp.bridge.units.a2j_running", return_value=up))


def test_stop_functions_stop_units_spawned_by_this_bridge():
    b = _b()
    tcp, outs, a2j = _probes(up=True)  # would still look up; ours, so stopping is success
    with tcp, outs, a2j, patch.object(b.processes, "stop", return_value=True) as stop:
        assert _stop_all(b) == [None, None, None]
    assert [c.args[0] for c in stop.call_args_list] == ["carla:main", "looper:engine", "a2j"]


def test_stop_functions_leave_adopted_running_units_alone():
    b = _b()
    tcp, outs, a2j = _probes(up=True)
    with tcp, outs, a2j, patch.object(b.processes, "stop", return_value=False):
        assert _stop_all(b) == [units.NOT_STARTED_BY_THIS_BRIDGE] * 3
    assert units.NOT_STARTED_BY_THIS_BRIDGE == "not started by this bridge; left running"


def test_stop_functions_treat_already_down_units_as_success():
    b = _b()
    tcp, outs, a2j = _probes(up=False)
    with tcp, outs, a2j, patch.object(b.processes, "stop", return_value=False):
        assert _stop_all(b) == [None, None, None]


def test_stop_carla_main_probes_the_rpc_port_of_this_config():
    b = _b()
    with patch("carla_mcp.bridge.units.tcp_reachable", return_value=True) as tcp, \
         patch.object(b.processes, "stop", return_value=False):
        asyncio.run(units.stop_carla_main(b))
    tcp.assert_called_once_with("127.0.0.1", b.config.carla_rpc_port)


def test_start_a2j_missing_binary():
    b = _b()
    with patch("carla_mcp.bridge.units.a2j_running", return_value=False), \
         patch.object(b.processes, "spawn", side_effect=FileNotFoundError):
        assert units.start_a2j(b) == "a2jmidid not installed"
