### Task 13: Looper MCP tools for the new engine commands

**Files:**
- Modify: `source/frontend/looper_mcp/tools.py` (append tools inside `register_tools`, after `load_session` ~line 330)
- Create: `source/frontend/looper_mcp/tests/test_rig_control_tools.py`

**Interfaces:**
- Consumes the Rust contract commands: `{"SaveSessionAt": "<abs dir>"}`, `{"SetMainOutputMute": bool}`, `{"SetAllOutputsMute": bool}`.
- Produces MCP tools: `save_session_at(path: str)`, `set_main_output_mute(muted: bool)`, `set_all_outputs_mute(muted: bool)` — thin `looper_client.send_command` wrappers formatted with `_format_result` (matches existing style at tools.py:321–330).

**Steps:**

- [ ] Write failing test `source/frontend/looper_mcp/tests/test_rig_control_tools.py`:

```python
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
```

- [ ] Run and see it fail: `uv run pytest source/frontend/looper_mcp/tests/test_rig_control_tools.py -v` — expect `KeyError: 'save_session_at'`.
- [ ] Append inside `register_tools` in `looper_mcp/tools.py` (after `load_session`):

```python
    @mcp_server.tool()
    async def save_session_at(path: str) -> str:
        """Save the looper session into exactly this directory (created if
        needed) — no auto-named subdirectory. Used by rig session saves."""
        result = await looper_client.send_command({"SaveSessionAt": path})
        return _format_result(result)

    @mcp_server.tool()
    async def set_main_output_mute(muted: bool) -> str:
        """Set (not toggle) main output mute — idempotent restore setter."""
        result = await looper_client.send_command({"SetMainOutputMute": muted})
        return _format_result(result)

    @mcp_server.tool()
    async def set_all_outputs_mute(muted: bool) -> str:
        """Set (not toggle) all-outputs mute — idempotent restore setter."""
        result = await looper_client.send_command({"SetAllOutputsMute": muted})
        return _format_result(result)
```

- [ ] Run pass: `uv run pytest source/frontend/looper_mcp/tests/ -v`
- [ ] Commit:
```
git add source/frontend/looper_mcp/tools.py source/frontend/looper_mcp/tests/test_rig_control_tools.py
git commit -m "feat(looper-mcp): save_session_at and idempotent mute setter tools

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

