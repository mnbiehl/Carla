"""PHASE-1 SHIM — deleted in phase 2.

Reaches the three rig verbs that still live inside the Carla process
(export_rig_state, import_rig_state, rig_handles) over the old FastMCP SSE
server.  Nothing else may use this module.
"""

from __future__ import annotations

import json
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.sse import sse_client

from carla_mcp.backends.rpc import RpcError

LEGACY_SSE_TIMEOUT_S = 30.0


def _unwrap(exc: BaseException) -> BaseException:
    """Follow a chain of (possibly nested) BaseExceptionGroups to the first real cause."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


async def call_tool(url: str, name: str, args: dict) -> Any:
    try:
        with anyio.fail_after(LEGACY_SSE_TIMEOUT_S):
            async with sse_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, args)
    except TimeoutError as exc:
        raise RpcError("backend_unavailable",
                       f"{name} timed out after {LEGACY_SSE_TIMEOUT_S:.0f}s") from exc
    except BaseExceptionGroup as exc:  # noqa: BLE001 — legacy boundary, gone in phase 2
        cause = _unwrap(exc)
        if isinstance(cause, TimeoutError):
            raise RpcError("backend_unavailable",
                           f"{name} timed out after {LEGACY_SSE_TIMEOUT_S:.0f}s") from cause
        raise RpcError("backend_unavailable", f"legacy sse {name}: {cause}") from cause
    except Exception as exc:  # noqa: BLE001 — legacy boundary, gone in phase 2
        raise RpcError("backend_unavailable", f"legacy sse {name}: {exc}") from exc

    text = "".join(getattr(c, "text", "") or "" for c in (getattr(result, "content", None) or []))
    if getattr(result, "isError", False):
        raise RpcError("internal", f"{name}: {text.strip() or 'legacy tool failed'}")
    try:
        return json.loads(text) if text.strip() else None
    except ValueError:
        return text
