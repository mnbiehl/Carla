"""Dynamic tool proxy for discovering and registering Carla MCP tools."""

import asyncio
import inspect
import logging
from typing import Any, Optional

from fastmcp.tools import Tool
from mcp.client.sse import sse_client
from mcp import ClientSession
from mcp.types import TextContent

logger = logging.getLogger(__name__)


# A forwarded call that outlives this gets an error reply instead of leaving
# the client waiting for its own (30 min) idle timeout.
FORWARD_TIMEOUT_S = 60.0

# Tools that legitimately run for minutes: plugin scans, project load/save and
# audio captures whose length the caller picks.
_SLOW_TOOL_TIMEOUT_S = 600.0
_SLOW_TOOLS = frozenset({
    "discover_all_plugins",
    "refresh_plugin_cache",
    "load_project",
    "save_project",
    "import_rig_state",
    "load_session",
    "save_session",
    "save_session_at",
    "capture_port_to_wav",
    "analyze_port_spectrum",
    "analyze_gain_staging",
})


def forward_timeout(tool_name: str) -> float:
    """Seconds a forwarded call to *tool_name* may run before it errors."""
    return _SLOW_TOOL_TIMEOUT_S if tool_name in _SLOW_TOOLS else FORWARD_TIMEOUT_S


# JSON Schema type string -> Python type
_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_schema_type(prop: dict) -> type:
    """Map a JSON Schema property dict to a Python type."""
    return _TYPE_MAP.get(prop.get("type", ""), Any)


async def _forward_tool_call(
    tool_name: str, args: dict, sse_url: str
) -> str:
    """Connect to Carla SSE and forward a tool call."""
    timeout = forward_timeout(tool_name)
    try:
        return await asyncio.wait_for(_call_once(tool_name, args, sse_url), timeout)
    except asyncio.TimeoutError:
        return (
            f"Error calling '{tool_name}': timed out after {timeout:.0f}s with no reply "
            f"from {sse_url}. The backend may be busy or wedged; check carla_status / "
            "looper_status."
        )
    except Exception as e:
        return f"Error calling '{tool_name}': {e}\n\nIs the backend running? Check with carla_status or looper_status."


async def _call_once(tool_name: str, args: dict, sse_url: str) -> str:
    """One SSE session: initialize, call *tool_name*, join its text parts."""
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


def _build_tool_function(
    name: str, input_schema: dict, sse_url: str
):
    """Build an async function with typed parameters from JSON Schema."""
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    # Build inspect.Parameter list: required first, then optional
    params = []
    for param_name in sorted(properties, key=lambda k: k not in required):
        prop = properties[param_name]
        py_type = _json_schema_type(prop)
        if param_name in required:
            params.append(
                inspect.Parameter(
                    param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=py_type,
                )
            )
        else:
            params.append(
                inspect.Parameter(
                    param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=None,
                    annotation=Optional[py_type],
                )
            )

    sig = inspect.Signature(params)

    # Build __annotations__ dict for pydantic/FastMCP compatibility
    annotations = {p.name: p.annotation for p in params}
    annotations["return"] = str

    async def wrapper(**kwargs):
        # Filter out None values (unset optional params)
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        return await _forward_tool_call(name, filtered, sse_url)

    wrapper.__name__ = name
    wrapper.__qualname__ = name
    wrapper.__signature__ = sig
    wrapper.__annotations__ = annotations

    return wrapper


# Module-level set tracking registered tool names
_registered_tools: set[str] = set()


def unregister_all(bridge, prefix: str = "") -> int:
    """Remove proxy tools from the bridge, optionally filtered by prefix."""
    count = 0
    prefix_str = f"{prefix}_" if prefix else ""
    for tool_name in list(_registered_tools):
        if prefix_str and not tool_name.startswith(prefix_str):
            continue
        try:
            bridge.remove_tool(tool_name)
            count += 1
        except Exception:
            logger.warning("Could not remove tool '%s'", tool_name)
        _registered_tools.discard(tool_name)
    return count


async def discover_and_register(bridge, sse_url: str, prefix: str = "") -> int:
    """Discover tools from an MCP backend and register them with optional prefix.

    Returns the number of tools registered, or 0 on connection error.
    """
    prefix_str = f"{prefix}_" if prefix else ""
    try:
        async with sse_client(sse_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()

                for tool in result.tools:
                    registered_name = f"{prefix_str}{tool.name}"
                    fn = _build_tool_function(
                        tool.name, tool.inputSchema, sse_url
                    )
                    tool_obj = Tool.from_function(
                        fn, name=registered_name, description=tool.description
                    )
                    bridge.add_tool(tool_obj)
                    _registered_tools.add(registered_name)

                return len(result.tools)
    except Exception as e:
        logger.warning("Failed to discover tools from %s: %s", sse_url, e)
        return 0
