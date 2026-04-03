"""Tests for start_rig tool."""

import asyncio
from unittest.mock import AsyncMock, patch

from carla_mcp.utils.pw_link import PwLinkResult

_TEST_CAPTURES = [
    "alsa_input.usb-Test_Interface-00.pro-input-0:capture_AUX0",
    "alsa_input.usb-Test_Interface-00.pro-input-0:capture_AUX1",
]
_TEST_MONITORS = [
    "alsa_output.usb-Test_Interface-00.pro-output-0:playback_AUX0",
    "alsa_output.usb-Test_Interface-00.pro-output-0:playback_AUX1",
]


@patch("carla_mcp.utils.pw_link.pw_link_verify", return_value=True)
@patch(
    "carla_mcp.utils.pw_link.pw_link_connect",
    return_value=PwLinkResult(success=True),
)
@patch("carla_mcp.utils.pw_link.find_capture_input_ports", return_value=_TEST_CAPTURES)
@patch("carla_mcp.utils.pw_link.find_monitor_output_ports", return_value=_TEST_MONITORS)
@patch(
    "carla_mcp.mcp_stdio_bridge._start_looper",
    new_callable=AsyncMock,
    return_value="Looper started.",
)
@patch(
    "carla_mcp.mcp_stdio_bridge._start_carla",
    new_callable=AsyncMock,
    return_value="Carla started.",
)
def test_start_rig_calls_carla_then_looper(
    mock_carla, mock_looper, mock_find_mon, mock_find_cap, mock_connect, mock_verify
):
    from carla_mcp.mcp_stdio_bridge import _start_rig

    result = asyncio.run(_start_rig())
    mock_carla.assert_called_once()
    mock_looper.assert_called_once()
    assert "Carla" in result
    assert "Looper" in result


@patch("carla_mcp.utils.pw_link.pw_link_verify", return_value=True)
@patch(
    "carla_mcp.utils.pw_link.pw_link_connect",
    return_value=PwLinkResult(success=True),
)
@patch("carla_mcp.utils.pw_link.find_capture_input_ports", return_value=_TEST_CAPTURES)
@patch("carla_mcp.utils.pw_link.find_monitor_output_ports", return_value=_TEST_MONITORS)
@patch(
    "carla_mcp.mcp_stdio_bridge._start_looper",
    new_callable=AsyncMock,
    return_value="ok",
)
@patch(
    "carla_mcp.mcp_stdio_bridge._start_carla",
    new_callable=AsyncMock,
    return_value="ok",
)
def test_start_rig_creates_pw_link_connections(
    mock_carla, mock_looper, mock_find_mon, mock_find_cap, mock_connect, mock_verify
):
    from carla_mcp.mcp_stdio_bridge import _start_rig

    result = asyncio.run(_start_rig())
    assert mock_connect.call_count == 4  # 4 external connections
    assert "Connections" in result
    assert "Verify" in result


@patch("carla_mcp.utils.pw_link.pw_link_verify", return_value=True)
@patch(
    "carla_mcp.utils.pw_link.pw_link_connect",
    return_value=PwLinkResult(success=True),
)
@patch("carla_mcp.utils.pw_link.find_capture_input_ports", return_value=_TEST_CAPTURES)
@patch("carla_mcp.utils.pw_link.find_monitor_output_ports", return_value=_TEST_MONITORS)
@patch(
    "carla_mcp.mcp_stdio_bridge._start_looper",
    new_callable=AsyncMock,
    return_value="ok",
)
@patch(
    "carla_mcp.mcp_stdio_bridge._start_carla",
    new_callable=AsyncMock,
    return_value="ok",
)
def test_start_rig_uses_discovered_ports(
    mock_carla, mock_looper, mock_find_mon, mock_find_cap, mock_connect, mock_verify
):
    from carla_mcp.mcp_stdio_bridge import _start_rig

    result = asyncio.run(_start_rig())
    assert mock_connect.call_count == 4
    connect_args = [c.args for c in mock_connect.call_args_list]
    for src, dst in connect_args:
        assert "Test_Interface" in src or "Test_Interface" in dst
