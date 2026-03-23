"""Tests for start_rig tool."""

import asyncio
from unittest.mock import AsyncMock, patch

from carla_mcp.utils.pw_link import PwLinkResult


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
def test_start_rig_calls_carla_then_looper(mock_carla, mock_looper):
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
    mock_carla, mock_looper, mock_connect, mock_verify
):
    from carla_mcp.mcp_stdio_bridge import _start_rig

    result = asyncio.run(_start_rig())
    assert mock_connect.call_count == 4  # 4 external connections
    assert "Connections" in result
    assert "Verify" in result
