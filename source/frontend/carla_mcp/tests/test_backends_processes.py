import subprocess
from unittest.mock import MagicMock, patch

import pytest

from carla_mcp.backends.processes import (
    CARLA_GUI_PGREP_PATTERN, ProcessManager, UnitSpec, a2j_running, carla_gui_running,
    ports_present, tcp_reachable,
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
    # Children must not read the bridge's MCP stdin or share its process group/session.
    assert popen.call_args.kwargs["stdin"] is subprocess.DEVNULL
    assert popen.call_args.kwargs["start_new_session"] is True
    log = popen.call_args.kwargs["stdout"]
    assert log.mode == "a" and log.name.endswith("carla:main.log")
    assert pm.is_running("carla:main") and pm.pid("carla:main") == 4242
    assert pm.names() == ["carla:main"]


def test_spawn_is_a_noop_when_already_running(tmp_path):
    pm = ProcessManager(tmp_path / "logs")
    with patch("carla_mcp.backends.processes.subprocess.Popen", return_value=_proc(4242)) as popen:
        first_pid = pm.spawn(UnitSpec(name="carla:main", argv=["pw-jack", "python3", "carla.py"]))
        log_before = pm._units["carla:main"].log
        second_pid = pm.spawn(UnitSpec(name="carla:main", argv=["pw-jack", "python3", "carla.py"]))
    assert popen.call_count == 1
    assert first_pid == second_pid == 4242
    assert pm._units["carla:main"].log is log_before


def test_spawn_respawns_after_process_exited(tmp_path):
    pm = ProcessManager(tmp_path / "logs")
    with patch("carla_mcp.backends.processes.subprocess.Popen",
               side_effect=[_proc(1, alive=False), _proc(2)]) as popen:
        first_pid = pm.spawn(UnitSpec(name="x", argv=["true"]))
        assert not pm.is_running("x")
        second_pid = pm.spawn(UnitSpec(name="x", argv=["true"]))
    assert popen.call_count == 2
    assert first_pid == 1 and second_pid == 2
    assert pm.is_running("x") and pm.pid("x") == 2


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


def test_spawn_oserror_closes_log_and_records_nothing(tmp_path):
    pm = ProcessManager(tmp_path / "logs")
    with patch("carla_mcp.backends.processes.subprocess.Popen", side_effect=OSError("pw-jack missing")):
        with pytest.raises(OSError):
            pm.spawn(UnitSpec(name="carla:main", argv=["pw-jack"]))
    assert not pm.is_running("carla:main") and pm.names() == []


def test_carla_gui_running_uses_pgrep_full_command_line():
    with patch("carla_mcp.backends.processes.subprocess.run", return_value=MagicMock(returncode=0)) as run:
        assert carla_gui_running() is True
    assert run.call_args.args[0] == ["pgrep", "-f", CARLA_GUI_PGREP_PATTERN]
    with patch("carla_mcp.backends.processes.subprocess.run", return_value=MagicMock(returncode=1)):
        assert carla_gui_running() is False
    with patch("carla_mcp.backends.processes.subprocess.run", side_effect=FileNotFoundError):
        assert carla_gui_running() is False
    with patch("carla_mcp.backends.processes.subprocess.run",
               side_effect=subprocess.TimeoutExpired("pgrep", 3)):
        assert carla_gui_running() is False


@pytest.mark.parametrize("cmdline, expected", [
    ("/usr/bin/python3 /home/m/carla-mcp-fork/source/frontend/carla.py", True),
    ("python3 carla.py", True),
    ("/usr/bin/python3.13 -X dev /x/carla.py --with-args", True),
    ("vim carla.py", False),
    ("python3 -m pytest tests/test_carla.py", False),
    ("uv run python -m carla_mcp.bridge", False),
])
def test_carla_gui_pattern_matches_interpreter_running_carla_py(cmdline, expected):
    import re
    assert bool(re.search(CARLA_GUI_PGREP_PATTERN, cmdline)) is expected
