"""Tests for chain launcher."""
import pytest
from unittest.mock import patch, Mock
from carla_mcp.orchestration.chain_launcher import ChainLauncher
from carla_mcp.state.instance_manager import InstanceManager


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
