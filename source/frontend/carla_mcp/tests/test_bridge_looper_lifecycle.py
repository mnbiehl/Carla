"""Tests for looper engine lifecycle — launch loopers binary before MCP server."""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open, call


@patch("carla_mcp.mcp_stdio_bridge.discover_and_register", return_value=5)
@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", side_effect=[False, True])
@patch("carla_mcp.mcp_stdio_bridge._is_looper_running", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_start_looper_makes_two_popen_calls(mock_popen, mock_running, mock_reachable, mock_discover):
    """_start_looper must make 2 Popen calls: engine first, then MCP."""
    from carla_mcp.mcp_stdio_bridge import _start_looper
    import carla_mcp.mcp_stdio_bridge as mod

    # Reset globals
    mod._looper_process = None
    mod._looper_log_file = None
    mod._looper_engine_process = None
    mod._looper_engine_log_file = None

    mock_proc = MagicMock()
    mock_proc.pid = 11111
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    # Mock subprocess.run for pw-link check
    with patch("carla_mcp.mcp_stdio_bridge.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="loopers:output_1", returncode=0)
        result = asyncio.run(_start_looper())

    assert mock_popen.call_count == 2, f"Expected 2 Popen calls, got {mock_popen.call_count}"


@patch("carla_mcp.mcp_stdio_bridge.discover_and_register", return_value=5)
@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", side_effect=[False, True])
@patch("carla_mcp.mcp_stdio_bridge._is_looper_running", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_first_popen_includes_pw_jack(mock_popen, mock_running, mock_reachable, mock_discover):
    """First Popen call must include pw-jack (engine launch)."""
    from carla_mcp.mcp_stdio_bridge import _start_looper
    import carla_mcp.mcp_stdio_bridge as mod

    mod._looper_process = None
    mod._looper_log_file = None
    mod._looper_engine_process = None
    mod._looper_engine_log_file = None

    mock_proc = MagicMock()
    mock_proc.pid = 11111
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    with patch("carla_mcp.mcp_stdio_bridge.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="loopers:output_1", returncode=0)
        result = asyncio.run(_start_looper())

    first_call_args = mock_popen.call_args_list[0][0][0]
    assert "pw-jack" in first_call_args, f"Expected pw-jack in first Popen call, got: {first_call_args}"


@patch("carla_mcp.mcp_stdio_bridge.discover_and_register", return_value=5)
@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge._is_looper_running", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_stop_looper_terminates_both_processes(mock_popen, mock_running, mock_reachable, mock_discover):
    """_stop_looper must terminate both the MCP and engine processes."""
    from carla_mcp.mcp_stdio_bridge import _stop_looper
    import carla_mcp.mcp_stdio_bridge as mod

    mock_mcp_proc = MagicMock()
    mock_mcp_proc.pid = 22222
    mock_mcp_proc.poll.return_value = None
    mock_mcp_proc.wait.return_value = 0

    mock_engine_proc = MagicMock()
    mock_engine_proc.pid = 33333
    mock_engine_proc.poll.return_value = None
    mock_engine_proc.wait.return_value = 0

    mod._looper_process = mock_mcp_proc
    mod._looper_engine_process = mock_engine_proc

    result = asyncio.run(_stop_looper())

    mock_mcp_proc.terminate.assert_called_once()
    mock_engine_proc.terminate.assert_called_once()


def test_loopers_path_configurable_via_env():
    """LOOPERS_PATH should be configurable via environment variable."""
    test_path = "/custom/path/to/loopers"
    with patch.dict(os.environ, {"LOOPERS_PATH": test_path}):
        # Re-import to pick up new env var
        import importlib
        import carla_mcp.mcp_stdio_bridge as mod
        importlib.reload(mod)
        assert mod.LOOPERS_PATH == test_path

    # Reload again to restore default
    import importlib
    import carla_mcp.mcp_stdio_bridge as mod
    importlib.reload(mod)


@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_is_looper_running_checks_both_processes(mock_popen):
    """_is_looper_running should check both engine and MCP processes."""
    import carla_mcp.mcp_stdio_bridge as mod

    # Both running
    mock_mcp = MagicMock()
    mock_mcp.poll.return_value = None
    mock_engine = MagicMock()
    mock_engine.poll.return_value = None
    mod._looper_process = mock_mcp
    mod._looper_engine_process = mock_engine
    assert mod._is_looper_running() is True

    # MCP dead, engine alive — not fully running
    mock_mcp.poll.return_value = 1
    mod._looper_process = mock_mcp
    mod._looper_engine_process = mock_engine
    assert mod._is_looper_running() is False

    # Both None
    mod._looper_process = None
    mod._looper_engine_process = None
    assert mod._is_looper_running() is False


@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_atexit_cleanup_terminates_engine(mock_popen):
    """_atexit_cleanup must also terminate _looper_engine_process."""
    import carla_mcp.mcp_stdio_bridge as mod

    mock_engine = MagicMock()
    mock_engine.poll.return_value = None
    mock_engine.wait.return_value = 0
    mod._looper_engine_process = mock_engine
    mod._looper_engine_log_file = MagicMock()

    # Also set looper MCP process to None so it doesn't interfere
    mod._looper_process = None
    mod._carla_process = None
    mod._carla_log_file = None

    mod._atexit_cleanup()

    mock_engine.terminate.assert_called_once()
