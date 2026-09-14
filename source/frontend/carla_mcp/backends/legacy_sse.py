"""PHASE-1 SHIM — deleted in phase 2.

Reaches the three rig verbs that still live inside the Carla process
(export_rig_state, import_rig_state, rig_handles) over the old FastMCP SSE
server.  Nothing else may use this module.
"""

from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

from carla_mcp.backends.rpc import RpcError


async def call_tool(url: str, name: str, args: dict) -> Any:
    try:
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, args)
    except Exception as exc:  # noqa: BLE001 — legacy boundary, gone in phase 2
        raise RpcError("backend_unavailable", f"legacy sse {name}: {exc}") from exc
    text = "".join(getattr(c, "text", "") or "" for c in (getattr(result, "content", None) or []))
    try:
        return json.loads(text) if text.strip() else None
    except ValueError:
        return text
