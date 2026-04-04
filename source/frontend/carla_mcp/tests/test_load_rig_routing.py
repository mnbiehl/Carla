"""Tests for load_rig_session external Carla wiring."""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock

from carla_mcp.utils.pw_link import PwLinkResult


@patch(
    "carla_mcp.utils.pw_link.find_capture_input_ports",
    return_value=["alsa_input.test:capture_AUX0", "alsa_input.test:capture_AUX1"],
)
@patch(
    "carla_mcp.utils.pw_link.ensure_carla_to_monitors",
    return_value={"connected": 1, "already_connected": 1, "failed": 0, "monitor_ports": ["m:0", "m:1"]},
)
@patch("carla_mcp.utils.pw_link.pw_link_connect", return_value=PwLinkResult(success=True))
@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", return_value=True)
@patch("carla_mcp.mcp_stdio_bridge._is_carla_reachable", return_value=True)
@patch("carla_mcp.mcp_stdio_bridge.sse_client")
def test_load_rig_session_wires_carla_externally(
    mock_sse, mock_carla_reach, mock_looper_reach,
    mock_connect, mock_ensure, mock_captures, tmp_path
):
    """load_rig_session should wire Carla to monitors and captures."""
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
            "version": 1,
            "backends": {
                "carla": {"running": True, "session": str(session_dir / "carla.carxp")},
                "looper": {"running": True, "session": str(session_dir / "looper.json")},
            },
        }
        (session_dir / "rig_manifest.json").write_text(json.dumps(manifest))

        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            from carla_mcp.mcp_stdio_bridge import load_rig_session
            result = asyncio.run(load_rig_session.fn("test-session"))

        mock_ensure.assert_called_once()
        # 2 capture connections (AUX0→in1, AUX1→in2)
        assert mock_connect.call_count == 2
        assert "Routing" in result
