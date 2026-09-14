import subprocess
from unittest.mock import MagicMock, patch

from carla_mcp.backends.processes import (
    ProcessManager, UnitSpec, a2j_running, ports_present, tcp_reachable,
)


def _proc(pid=100, alive=True):
    p = MagicMock()
    p.pid = pid
    p.poll.return_value = None if alive else 0
    return p


def test_spawn_opens_append_log_and_records_pid(tmp_path):
    pm = ProcessManager(tmp_path / "logs")
    with patch("carla_mcp.backends.processes.subprocess.Popen", return_value=_proc(4242)) as popen:
        pid = pm.spawn(UnitSpec(name="carla:main", argv=["pw-jack", "python3", "carla.py"],
                                cwd="/x", env={"A": "1"}))
    assert pid == 4242
    assert popen.call_args.args[0] == ["pw-jack", "python3", "carla.py"]
    assert popen.call_args.kwargs["cwd"] == "/x" and popen.call_args.kwargs["env"] == {"A": "1"}
    log = popen.call_args.kwargs["stdout"]
    assert log.mode == "a" and log.name.endswith("carla:main.log")
    assert pm.is_running("carla:main") and pm.pid("carla:main") == 4242
    assert pm.names() == ["carla:main"]


def test_exited_process_is_forgotten(tmp_path):
    pm = ProcessManager(tmp_path)
    with patch("carla_mcp.backends.processes.subprocess.Popen", return_value=_proc(alive=False)):
        pm.spawn(UnitSpec(name="x", argv=["true"]))
    assert not pm.is_running("x") and pm.pid("x") is None and pm.stop("x") is None


def test_stop_terminates_then_kills(tmp_path):
    pm = ProcessManager(tmp_path)
    proc = _proc()
    proc.wait.side_effect = [subprocess.TimeoutExpired("x", 1), 0]
    with patch("carla_mcp.backends.processes.subprocess.Popen", return_value=proc):
        pm.spawn(UnitSpec(name="x", argv=["sleep"]))
    assert pm.stop("x", timeout=0.01) is None
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()
    assert not pm.is_running("x")


def test_tcp_reachable_false_on_closed_port():
    assert tcp_reachable("127.0.0.1", 1) is False


def test_a2j_running_uses_pgrep():
    with patch("carla_mcp.backends.processes.subprocess.run", return_value=MagicMock(returncode=0)):
        assert a2j_running() is True
    with patch("carla_mcp.backends.processes.subprocess.run", side_effect=FileNotFoundError):
        assert a2j_running() is False


def test_ports_present():
    assert ports_present("loopers:", lambda: ["loopers:loop0_out_l"]) is True
    assert ports_present("loopers:", lambda: ["Carla:audio-out1"]) is False
