"""Tests for configurable Python path via CARLA_PYTHON_PATH env var."""
import os
import pytest
from unittest.mock import patch, Mock
from carla_mcp.state.instance_manager import InstanceManager


class TestConfigurablePythonPath:
    def test_chain_launcher_uses_env_python(self):
        """With CARLA_PYTHON_PATH set, the constant picks it up."""
        with patch.dict(os.environ, {"CARLA_PYTHON_PATH": "/opt/custom/python3"}):
            # Re-import to pick up the env var
            import importlib
            import carla_mcp.orchestration.chain_launcher as mod
            importlib.reload(mod)
            assert mod.CARLA_PYTHON_PATH == "/opt/custom/python3"

    def test_chain_launcher_defaults_to_usr_bin_python3(self):
        """Without env var, defaults to /usr/bin/python3."""
        env = os.environ.copy()
        env.pop("CARLA_PYTHON_PATH", None)
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import carla_mcp.orchestration.chain_launcher as mod
            importlib.reload(mod)
            assert mod.CARLA_PYTHON_PATH == "/usr/bin/python3"

    def test_launch_uses_configured_python(self):
        """Verify Popen command uses CARLA_PYTHON_PATH."""
        with patch.dict(os.environ, {"CARLA_PYTHON_PATH": "/opt/custom/python3"}):
            import importlib
            import carla_mcp.orchestration.chain_launcher as mod
            importlib.reload(mod)

            mgr = InstanceManager(base_mcp_port=3002)
            launcher = mod.ChainLauncher(instance_manager=mgr, carla_script="/fake/carla.py")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock(poll=Mock(return_value=None))
                launcher.launch("test_chain")
                cmd = mock_popen.call_args[0][0]
                assert cmd[1] == "/opt/custom/python3"
