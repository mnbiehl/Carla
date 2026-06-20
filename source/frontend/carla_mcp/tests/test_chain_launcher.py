"""Tests for chain launcher."""
import subprocess
import pytest
from unittest.mock import patch, Mock
from carla_mcp.orchestration.chain_launcher import ChainLauncher
from carla_mcp.state.instance_manager import InstanceManager


@pytest.fixture(autouse=True)
def _all_ports_free():
    """Treat every candidate port as free so allocation is deterministic.

    allocate_port() bind-tests each port against loopback; these launcher
    tests assert exact port numbers, so stub the probe to keep them
    independent of whatever is bound on the test host.
    """
    with patch.object(InstanceManager, "_port_in_use", return_value=False):
        yield


class TestChainLauncherLaunch:
    def test_launch_creates_instance(self):
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock(poll=Mock(return_value=None))
            instance = launcher.launch("guitar")
            assert instance.name == "guitar"
            assert instance.mcp_port == 3002
            assert instance.jack_client_name == "CarlaChain_guitar"
            assert instance.is_running

    def test_launch_sets_env_vars(self):
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock(poll=Mock(return_value=None))
            launcher.launch("guitar")
            env = mock_popen.call_args.kwargs["env"]
            assert env["CARLA_MCP_PORT"] == "3002"
            assert env["CARLA_CLIENT_NAME"] == "CarlaChain_guitar"

    def test_launch_registers_instance(self):
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock(poll=Mock(return_value=None))
            launcher.launch("guitar")
            assert mgr.get("guitar") is not None

    def test_launch_duplicate_name_raises(self):
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock(poll=Mock(return_value=None))
            launcher.launch("guitar")
            with pytest.raises(ValueError, match="already exists"):
                launcher.launch("guitar")

    def test_launch_releases_port_and_log_on_spawn_failure(self):
        # If Popen raises, the allocated port and log FD must not leak —
        # nothing gets registered, so terminate() could never clean up.
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        with patch("subprocess.Popen", side_effect=OSError("exec failed")):
            with pytest.raises(OSError):
                launcher.launch("guitar")
        assert mgr.allocate_port() == 3002  # port was released for reuse
        assert "guitar" not in launcher._log_files  # log handle not leaked
        assert mgr.get("guitar") is None  # not registered


class TestChainLauncherTerminate:
    def test_terminate_stops_process(self):
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        with patch("subprocess.Popen", return_value=mock_proc):
            launcher.launch("guitar")
        launcher.terminate("guitar")
        mock_proc.terminate.assert_called_once()
        assert mgr.get("guitar") is None

    def test_terminate_nonexistent_raises(self):
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        with pytest.raises(ValueError, match="not found"):
            launcher.terminate("nonexistent")

    def test_terminate_reaps_already_exited_process(self):
        # A child that exited on its own must still be wait()ed, or it
        # lingers as a zombie.  Don't SIGTERM a dead process.
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        mock_proc = Mock()
        mock_proc.poll.return_value = None  # running at launch
        with patch("subprocess.Popen", return_value=mock_proc):
            launcher.launch("guitar")
        mock_proc.poll.return_value = 0  # has since exited
        launcher.terminate("guitar")
        mock_proc.terminate.assert_not_called()
        mock_proc.wait.assert_called_once()
        assert mgr.get("guitar") is None

    def test_terminate_kills_and_reaps_on_timeout(self):
        # A child that ignores SIGTERM is killed, then wait()ed again to reap.
        mgr = InstanceManager(base_mcp_port=3002)
        launcher = ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="carla", timeout=5),
            0,
        ]
        with patch("subprocess.Popen", return_value=mock_proc):
            launcher.launch("guitar")
        launcher.terminate("guitar")
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2
        assert mgr.get("guitar") is None
