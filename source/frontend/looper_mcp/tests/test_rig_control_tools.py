"""Tests for the managed-rig looper tools: SaveSessionAt and mute setters."""

import asyncio
from unittest.mock import AsyncMock

from fastmcp import FastMCP

from looper_mcp.tools import register_tools


def _server_and_client():
    server = FastMCP("test")
    client = AsyncMock()
    client.send_command = AsyncMock(return_value={"ok": None})
    register_tools(server, client)
    return server, client


def _tool(server, name):
    return server._tool_manager._tools[name].fn


def test_save_session_at_sends_exact_command():
    server, client = _server_and_client()
    result = asyncio.run(_tool(server, "save_session_at")("/abs/dir"))
    client.send_command.assert_awaited_once_with({"SaveSessionAt": "/abs/dir"})
    assert result == "OK"


def test_set_main_output_mute_sends_bool():
    server, client = _server_and_client()
    asyncio.run(_tool(server, "set_main_output_mute")(True))
    client.send_command.assert_awaited_once_with({"SetMainOutputMute": True})


def test_set_all_outputs_mute_sends_bool():
    server, client = _server_and_client()
    asyncio.run(_tool(server, "set_all_outputs_mute")(False))
    client.send_command.assert_awaited_once_with({"SetAllOutputsMute": False})


def test_error_response_is_surfaced():
    server, client = _server_and_client()
    client.send_command = AsyncMock(return_value={"error": "no session"})
    result = asyncio.run(_tool(server, "save_session_at")("/abs/dir"))
    assert result == "Error: no session"
