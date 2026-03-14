"""Dynamic tool proxy for discovering and registering Carla MCP tools."""

import inspect
import logging
from typing import Any, Optional

from mcp.client.sse import sse_client
from mcp import ClientSession
from mcp.types import TextContent

logger = logging.getLogger(__name__)


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
            return "\n".join(parts)


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

    async def wrapper(**kwargs):
        # Filter out None values (unset optional params)
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        return await _forward_tool_call(name, filtered, sse_url)

    wrapper.__name__ = name
    wrapper.__qualname__ = name
    wrapper.__signature__ = sig

    return wrapper
