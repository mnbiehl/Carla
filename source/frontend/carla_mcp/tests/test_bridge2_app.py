import asyncio
import subprocess
from unittest.mock import patch

from carla_mcp.backends.processes import tcp_reachable
from carla_mcp.bridge.app import Bridge, _git_rev
from carla_mcp.bridge.config import BridgeConfig


def test_for_tests_never_targets_live_rig_ports():
    b = Bridge.for_tests()
    assert b.config.carla_rpc_port not in (8088, 8089)
    assert b.config.looper_port not in (8088, 8089)
    assert b.carla.rpc.transport.port == b.config.carla_rpc_port
    assert b.looper.transport.port == b.config.looper_port
    assert b.carla.rpc.transport.port not in (8088, 8089)
    assert b.looper.transport.port not in (8088, 8089)


def test_for_tests_ports_refuse_fast():
    b = Bridge.for_tests()
    assert tcp_reachable("127.0.0.1", b.config.carla_rpc_port, timeout=1.0) is False
    assert tcp_reachable("127.0.0.1", b.config.looper_port, timeout=1.0) is False
    assert asyncio.run(b.carla.rpc.transport.reachable()) is False
    assert asyncio.run(b.looper.reachable()) is False


def test_for_tests_env_override_still_wins(tmp_path):
    b = Bridge.for_tests(env={"HOME": str(tmp_path), "CARLA_RPC_PORT": "1", "LOOPER_JSON_PORT": "1",
                              "RIG_SESSION_DIR": str(tmp_path / "sessions")})
    assert b.config.session_dir == tmp_path / "sessions"


def test_git_rev_handles_any_oserror(tmp_path):
    cfg = BridgeConfig.from_env({"HOME": str(tmp_path)})
    with patch("subprocess.run", side_effect=PermissionError("nope")):
        assert _git_rev(cfg) == "unknown"
    with patch("subprocess.run", side_effect=FileNotFoundError("no git")):
        assert _git_rev(cfg) == "unknown"
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 3)):
        assert _git_rev(cfg) == "unknown"
