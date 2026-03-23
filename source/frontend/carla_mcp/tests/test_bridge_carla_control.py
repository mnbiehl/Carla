"""Tests that carla_start launches carla-control, not carla.py."""

import pytest
from unittest.mock import patch, MagicMock, mock_open


@patch("carla_mcp.mcp_stdio_bridge.discover_and_register", return_value=5)
@patch("carla_mcp.mcp_stdio_bridge._is_carla_reachable", side_effect=[False, True])
@patch("carla_mcp.mcp_stdio_bridge._is_carla_running", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_carla_start_launches_carla_control(mock_popen, mock_running, mock_reachable, mock_discover):
    """carla_start must launch carla-control, not carla.py."""
    import asyncio
    from carla_mcp.mcp_stdio_bridge import _start_carla

    mock_proc = MagicMock()
    mock_proc.pid = 12345
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    result = asyncio.run(_start_carla())

    # Verify carla-control is in the command
    args = mock_popen.call_args[0][0]
    assert "carla-control" in " ".join(str(a) for a in args), f"Expected carla-control in launch command, got: {args}"
    assert "carla.py" not in " ".join(str(a) for a in args), f"carla.py should not be in launch command, got: {args}"
