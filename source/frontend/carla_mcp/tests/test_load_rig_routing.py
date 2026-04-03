"""Tests for load_rig_session routing restoration."""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock

from carla_mcp.utils.pw_link import PwLinkResult


@patch("carla_mcp.utils.pw_link.wait_for_ports", return_value=True)
@patch("carla_mcp.utils.pw_link.pw_link_connect", return_value=PwLinkResult(success=True))
@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", return_value=True)
@patch("carla_mcp.mcp_stdio_bridge._is_carla_reachable", return_value=True)
@patch("carla_mcp.mcp_stdio_bridge.sse_client")
def test_load_rig_session_restores_routing(
    mock_sse, mock_carla_reach, mock_looper_reach, mock_connect, mock_wait, tmp_path
):
    """load_rig_session should replay saved routing entries."""
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock()
    mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))

    with patch("carla_mcp.mcp_stdio_bridge.ClientSession") as mock_cs:
        mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

        session_dir = tmp_path / "test-session"
        session_dir.mkdir()
        manifest = {
            "version": 2,
            "backends": {
                "carla": {"running": True, "session": str(session_dir / "carla.carxp")},
                "looper": {"running": True, "session": str(session_dir / "looper.json")},
            },
            "routing": [
                {"src": "loopers:loop0_out_l", "dst": "Carla:audio-in3"},
                {"src": "loopers:loop0_out_r", "dst": "Carla:audio-in4"},
                {"src": "Carla:audio-out1", "dst": "alsa_output.test:playback_AUX0"},
            ],
        }
        (session_dir / "rig_manifest.json").write_text(json.dumps(manifest))

        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            from carla_mcp.mcp_stdio_bridge import load_rig_session
            result = asyncio.run(load_rig_session.fn("test-session"))

        assert mock_connect.call_count == 3
        assert "3/3" in result or "Routing" in result


@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", return_value=True)
@patch("carla_mcp.mcp_stdio_bridge._is_carla_reachable", return_value=True)
@patch("carla_mcp.mcp_stdio_bridge.sse_client")
def test_load_v1_manifest_skips_routing(
    mock_sse, mock_carla_reach, mock_looper_reach, tmp_path
):
    """v1 manifest (no routing key) should load without error."""
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock()
    mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))

    with patch("carla_mcp.mcp_stdio_bridge.ClientSession") as mock_cs:
        mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

        session_dir = tmp_path / "old-session"
        session_dir.mkdir()
        manifest = {
            "version": 1,
            "backends": {
                "carla": {"running": True, "session": str(session_dir / "carla.carxp")},
                "looper": {"running": True, "session": str(session_dir / "looper.json")},
            },
        }
        (session_dir / "rig_manifest.json").write_text(json.dumps(manifest))

        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            from carla_mcp.mcp_stdio_bridge import load_rig_session
            result = asyncio.run(load_rig_session.fn("old-session"))

        assert "Routing" not in result
