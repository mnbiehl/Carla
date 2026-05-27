"""
RemoteInstance: typed async client for a child Carla MCP server.

Each child Carla process exposes the full MCP tool surface over SSE.
RemoteInstance wraps a caller callable so that the SSE transport is
injectable for tests while the production path uses the same
sse_client/ClientSession pattern as tool_proxy._forward_tool_call.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from mcp.client.sse import sse_client
from mcp import ClientSession
from mcp.types import TextContent


class RemoteInstance:
    """Typed async client for a child Carla MCP instance.

    Args:
        call_tool: Async callable ``(tool_name: str, args: dict) -> str``
                   that forwards a tool call and returns the raw text response.
    """

    def __init__(self, call_tool: Callable[[str, dict], Awaitable[str]]) -> None:
        self._call_tool = call_tool

    @classmethod
    def over_sse(cls, sse_url: str) -> "RemoteInstance":
        """Build a RemoteInstance that connects to *sse_url* for each call.

        Uses one SSE connection per call (matches tool_proxy pattern).

        Args:
            sse_url: Full SSE endpoint, e.g. "http://127.0.0.1:8090/sse"
        """

        async def _call(tool_name: str, args: dict) -> str:
            try:
                async with sse_client(sse_url) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, args)
                        parts = []
                        for content in result.content:
                            if isinstance(content, TextContent):
                                parts.append(content.text)
                            else:
                                parts.append(str(content))
                        return "\n".join(parts) if parts else "OK"
            except Exception as e:
                return f"Error calling '{tool_name}': {e}"

        return cls(_call)

    # ------------------------------------------------------------------
    # Low-level passthrough

    async def call(self, tool_name: str, **args: Any) -> str:
        """Forward an arbitrary tool call to the child instance.

        Args:
            tool_name: Name of the child's MCP tool.
            **args:    Keyword arguments passed as the tool's input dict.

        Returns:
            Raw response string from the child.
        """
        return await self._call_tool(tool_name, args)

    # ------------------------------------------------------------------
    # Typed convenience methods

    async def add_plugin(self, plugin_name: str, plugin_type: str | None = None) -> str:
        """Add a plugin by name on the child instance.

        Args:
            plugin_name: Human-readable plugin name to search for.
            plugin_type: Optional plugin type filter (lv2, vst2, etc.).

        Returns:
            Raw response string from the child's add_plugin_by_name tool.
        """
        args: dict[str, Any] = {"plugin_name": plugin_name}
        if plugin_type is not None:
            args["plugin_type"] = plugin_type
        return await self._call_tool("add_plugin_by_name", args)

    async def remove_plugin(self, plugin_id: int) -> str:
        """Remove a plugin from the child instance.

        Args:
            plugin_id: Plugin ID (0-based) to remove.

        Returns:
            Raw response string from the child's remove_plugin tool.
        """
        return await self._call_tool("remove_plugin", {"plugin_id": plugin_id})

    async def set_parameter(self, plugin_id: int, parameter_id: int, value: float) -> str:
        """Set a plugin parameter value on the child instance.

        Args:
            plugin_id:    Plugin ID (0-based).
            parameter_id: Parameter index within that plugin.
            value:        New parameter value.

        Returns:
            Raw response string from the child's set_plugin_parameter tool.
        """
        return await self._call_tool(
            "set_plugin_parameter",
            {"plugin_id": plugin_id, "parameter_id": parameter_id, "value": value},
        )

    async def set_handle(self, plugin_id: int, handle: str) -> str:
        """Stamp a stable handle onto a plugin on the child instance.

        Args:
            plugin_id: Plugin ID (0-based).
            handle:    Stable handle string, e.g. "strat/comp".

        Returns:
            Raw response string from the child's set_plugin_handle tool.
        """
        return await self._call_tool(
            "set_plugin_handle", {"plugin_id": plugin_id, "handle": handle}
        )

    async def list_handles(self) -> dict[int, str]:
        """Return all plugin handles on the child instance as {plugin_id: handle}.

        Makes a single round-trip to the child's list_plugin_handles tool and
        parses the returned JSON object.

        Returns:
            Dict mapping integer plugin IDs to their handle strings.
        """
        raw = await self._call_tool("list_plugin_handles", {})
        try:
            data: dict[str, str] = json.loads(raw)
            return {int(k): v for k, v in data.items()}
        except (json.JSONDecodeError, ValueError):
            return {}

    async def resolve_handle(self, handle: str) -> int | None:
        """Find the plugin_id whose handle matches *handle* on the child instance.

        Makes exactly one call (list_handles) and searches the result locally.

        Args:
            handle: The stable handle to look up, e.g. "strat/comp".

        Returns:
            The matching plugin_id (int) if found, otherwise None.
        """
        handles = await self.list_handles()
        for pid, h in handles.items():
            if h == handle:
                return pid
        return None
