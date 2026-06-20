"""FIX 3: rig session must save/restore external JACK (pw-link) routing.

A non-standard pw-link routing (e.g. a looper output wired to a Carla input)
must survive a save/load round-trip. Backward compatibility: a v1 manifest
with no "routing" key must still load via the static fallback wiring.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from carla_mcp.mcp_stdio_bridge import _build_rig_manifest
from carla_mcp.utils.pw_link import PwLinkResult


# ---------------------------------------------------------------------------
# Manifest shape (version bump + routing key)
# ---------------------------------------------------------------------------

def test_manifest_version_bumped_to_2():
    """Manifest must be version 2 once routing is captured."""
    manifest = _build_rig_manifest(
        carla_running=True,
        looper_running=True,
        carla_session="c.carxp",
        looper_session="l.json",
    )
    assert manifest["version"] == 2


def test_manifest_stores_routing():
    """A routing list passed in must be stored under the 'routing' key."""
    routing = [["loopers:out_1", "Carla:audio-in1"], ["loopers:out_2", "Carla:audio-in2"]]
    manifest = _build_rig_manifest(
        carla_running=True,
        looper_running=True,
        routing=routing,
    )
    assert manifest["routing"] == routing


def test_manifest_routing_defaults_empty():
    """Without routing the key must still exist (empty list)."""
    manifest = _build_rig_manifest(carla_running=False, looper_running=False)
    assert manifest.get("routing") == []


# ---------------------------------------------------------------------------
# save_rig_session captures live pw-link connections
# ---------------------------------------------------------------------------

@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", return_value=False)
@patch("carla_mcp.mcp_stdio_bridge._is_carla_reachable", return_value=False)
def test_save_captures_live_routing(mock_carla, mock_looper, tmp_path):
    """save_rig_session must capture live connections via JackRouter and write
    them into the manifest under 'routing'."""
    live = [("loopers:out_1", "Carla:audio-in1"), ("loopers:out_2", "Carla:audio-in2")]

    mock_router = MagicMock()
    mock_router.list_connections = MagicMock(return_value=live)

    with patch("carla_mcp.mcp_stdio_bridge.JackRouter", return_value=mock_router):
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            from carla_mcp.mcp_stdio_bridge import save_rig_session
            asyncio.run(save_rig_session.fn("test-session"))

    # list_connections should have been called filtering loopers/Carla prefixes
    mock_router.list_connections.assert_called_once()
    _, kwargs = mock_router.list_connections.call_args
    prefixes = kwargs.get("filter_prefixes") or (
        mock_router.list_connections.call_args.args[0]
        if mock_router.list_connections.call_args.args else None
    )
    assert prefixes is not None
    assert "loopers:" in prefixes and "Carla:" in prefixes

    manifest = json.loads((tmp_path / "test-session" / "rig_manifest.json").read_text())
    assert manifest["version"] == 2
    # Routing entries are stored (as lists after JSON round-trip).
    assert [list(c) for c in live] == [list(c) for c in manifest["routing"]]


# ---------------------------------------------------------------------------
# load_rig_session replays saved routing
# ---------------------------------------------------------------------------

@patch(
    "carla_mcp.utils.pw_link.find_capture_input_ports",
    return_value=[],
)
@patch(
    "carla_mcp.utils.pw_link.ensure_carla_to_monitors",
    return_value={"connected": 0, "already_connected": 0, "failed": 0, "monitor_ports": []},
)
@patch("carla_mcp.utils.pw_link.pw_link_connect", return_value=PwLinkResult(success=True))
@patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", return_value=True)
@patch("carla_mcp.mcp_stdio_bridge._is_carla_reachable", return_value=True)
@patch("carla_mcp.mcp_stdio_bridge.sse_client")
def test_load_replays_saved_routing(
    mock_sse, mock_carla, mock_looper, mock_connect, mock_ensure, mock_caps, tmp_path
):
    """A v2 manifest with routing entries must replay each saved connection."""
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock()
    mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))

    routing = [["loopers:out_1", "Carla:audio-in1"], ["loopers:out_2", "Carla:audio-in2"]]

    with patch("carla_mcp.mcp_stdio_bridge.ClientSession") as mock_cs:
        mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

        session_dir = tmp_path / "rt-session"
        session_dir.mkdir()
        manifest = {
            "version": 2,
            "backends": {
                "carla": {"running": True, "session": str(session_dir / "carla.carxp")},
                "looper": {"running": True, "session": str(session_dir / "looper.json")},
            },
            "routing": routing,
        }
        (session_dir / "rig_manifest.json").write_text(json.dumps(manifest))

        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            from carla_mcp.mcp_stdio_bridge import load_rig_session
            result = asyncio.run(load_rig_session.fn("rt-session"))

    # Each saved routing connection should be replayed.
    replayed = {
        (c.args[0], c.args[1]) for c in mock_connect.call_args_list
    }
    for src, dst in routing:
        assert (src, dst) in replayed, f"missing replay of {src} -> {dst}"
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Backward compat: v1 manifest with no routing key still loads
# ---------------------------------------------------------------------------

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
def test_load_v1_manifest_no_routing_still_loads(
    mock_sse, mock_carla, mock_looper, mock_connect, mock_ensure, mock_caps, tmp_path
):
    """A legacy v1 manifest (no 'routing' key) must load without error and fall
    back to the static wiring (ensure_carla_to_monitors + capture wiring)."""
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock()
    mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))

    with patch("carla_mcp.mcp_stdio_bridge.ClientSession") as mock_cs:
        mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

        session_dir = tmp_path / "v1-session"
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
            result = asyncio.run(load_rig_session.fn("v1-session"))

    # Static fallback wiring still runs.
    mock_ensure.assert_called_once()
    assert "Routing" in result
