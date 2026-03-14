"""Dynamic tool proxy for discovering and registering Carla MCP tools."""

from typing import Any


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
