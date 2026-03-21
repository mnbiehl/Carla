import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from looper_mcp.looper_client import LooperClient


@pytest.mark.asyncio
async def test_send_command_returns_ok():
    """Sending a valid command returns True."""
    client = LooperClient(host="127.0.0.1", port=8088)
    mock_reader = AsyncMock()
    mock_reader.readline = AsyncMock(return_value=b'{"ok": true}\n')
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    with patch("looper_mcp.looper_client.asyncio.open_connection",
               return_value=(mock_reader, mock_writer)):
        result = await client.send_command({"Start": None})
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_send_command_returns_error():
    """Error from looperdooper is returned as dict."""
    client = LooperClient(host="127.0.0.1", port=8088)
    mock_reader = AsyncMock()
    mock_reader.readline = AsyncMock(return_value=b'{"error": "bad command"}\n')
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    with patch("looper_mcp.looper_client.asyncio.open_connection",
               return_value=(mock_reader, mock_writer)):
        result = await client.send_command({"Bad": None})
    assert result == {"error": "bad command"}


@pytest.mark.asyncio
async def test_get_state_returns_snapshot():
    """GetState returns engine state dict."""
    client = LooperClient(host="127.0.0.1", port=8088)
    state = {"state": {"tempo_bpm": 120.0, "looper_count": 2}}
    mock_reader = AsyncMock()
    mock_reader.readline = AsyncMock(return_value=json.dumps(state).encode() + b"\n")
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    with patch("looper_mcp.looper_client.asyncio.open_connection",
               return_value=(mock_reader, mock_writer)):
        result = await client.get_state()
    assert result["state"]["tempo_bpm"] == 120.0


@pytest.mark.asyncio
async def test_send_command_connection_refused():
    """Connection refused raises ConnectionError."""
    client = LooperClient(host="127.0.0.1", port=8088)
    with patch("looper_mcp.looper_client.asyncio.open_connection",
               side_effect=ConnectionRefusedError()):
        with pytest.raises(ConnectionError):
            await client.send_command({"Start": None})
