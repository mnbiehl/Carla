"""Children of the stdio bridge must never share its MCP stdin.

The bridge speaks JSON-RPC over stdin/stdout. A child that inherits stdin and
reads it (``loopers`` headless mode reads lines looking for ``q``) steals
requests, and those tool calls never get a reply.
"""

import asyncio
import subprocess
from unittest.mock import MagicMock, mock_open, patch

import carla_mcp.mcp_stdio_bridge as mod


def _fake_proc():
    proc = MagicMock()
    proc.pid = 4242
    proc.poll.return_value = None
    return proc


def _assert_detached(mock_popen):
    assert mock_popen.call_count > 0
    for c in mock_popen.call_args_list:
        assert c.kwargs.get("stdin") is subprocess.DEVNULL, c
        assert c.kwargs.get("start_new_session") is True, c


@patch("carla_mcp.mcp_stdio_bridge.discover_and_register", return_value=5)
@patch("carla_mcp.mcp_stdio_bridge._is_carla_reachable", side_effect=[False, True])
@patch("carla_mcp.mcp_stdio_bridge._is_carla_running", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_carla_child_is_detached_from_stdin(mock_popen, _running, _reachable, _discover):
    mod._carla_process = None
    mock_popen.return_value = _fake_proc()
    with patch("carla_mcp.mcp_stdio_bridge.asyncio.sleep", return_value=None):
        asyncio.run(mod._start_carla())
    _assert_detached(mock_popen)


@patch("carla_mcp.mcp_stdio_bridge.discover_and_register", return_value=5)
@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", side_effect=[False, True])
@patch("carla_mcp.mcp_stdio_bridge._is_looper_running", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_looper_children_are_detached_from_stdin(mock_popen, _running, _reachable, _discover):
    mod._looper_process = None
    mod._looper_engine_process = None
    mock_popen.return_value = _fake_proc()
    with patch("carla_mcp.mcp_stdio_bridge.subprocess.run") as mock_run, patch(
        "carla_mcp.mcp_stdio_bridge.asyncio.sleep", return_value=None
    ):
        mock_run.return_value = MagicMock(stdout="loopers:output_1", returncode=0)
        asyncio.run(mod._start_looper())
    assert mock_popen.call_count == 2
    _assert_detached(mock_popen)


@patch("carla_mcp.mcp_stdio_bridge._is_a2j_running", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
@patch("builtins.open", mock_open())
def test_a2j_child_is_detached_from_stdin(mock_popen, _running):
    mod._a2j_process = None
    mock_popen.return_value = _fake_proc()
    assert mod._start_a2j() is None
    _assert_detached(mock_popen)
