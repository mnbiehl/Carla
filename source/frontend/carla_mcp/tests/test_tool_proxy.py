import asyncio
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from carla_mcp.tool_proxy import (
    _json_schema_type,
    _build_tool_function,
    discover_and_register,
    unregister_all,
    _registered_tools,
)


def test_string_type():
    assert _json_schema_type({"type": "string"}) is str


def test_integer_type():
    assert _json_schema_type({"type": "integer"}) is int


def test_number_type():
    assert _json_schema_type({"type": "number"}) is float


def test_boolean_type():
    assert _json_schema_type({"type": "boolean"}) is bool


def test_array_type():
    assert _json_schema_type({"type": "array"}) is list


def test_object_type():
    assert _json_schema_type({"type": "object"}) is dict


def test_missing_type():
    from typing import Any
    assert _json_schema_type({}) is Any


def test_unknown_type():
    from typing import Any
    assert _json_schema_type({"type": "null"}) is Any


# --- Task 2: Build Typed Wrapper Functions ---


def test_build_function_name():
    schema = {"properties": {"query": {"type": "string"}}, "required": ["query"]}
    fn = _build_tool_function("search_plugins", schema, "http://localhost:3001/sse")
    assert fn.__name__ == "search_plugins"


def test_build_function_has_required_param():
    schema = {"properties": {"query": {"type": "string"}}, "required": ["query"]}
    fn = _build_tool_function("search_plugins", schema, "http://localhost:3001/sse")
    sig = inspect.signature(fn)
    param = sig.parameters["query"]
    assert param.annotation is str
    assert param.default is inspect.Parameter.empty


def test_build_function_has_optional_param():
    schema = {
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"],
    }
    fn = _build_tool_function("search_plugins", schema, "http://localhost:3001/sse")
    sig = inspect.signature(fn)
    assert sig.parameters["limit"].default is None


def test_build_function_no_params():
    schema = {"properties": {}, "required": []}
    fn = _build_tool_function("list_plugins", schema, "http://localhost:3001/sse")
    sig = inspect.signature(fn)
    assert len(sig.parameters) == 0


def test_build_function_is_async():
    schema = {"properties": {}, "required": []}
    fn = _build_tool_function("list_plugins", schema, "http://localhost:3001/sse")
    assert inspect.iscoroutinefunction(fn)


# --- Task 3: Discover and Register / Unregister All ---


def _make_mock_tool(name, description, input_schema):
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.inputSchema = input_schema
    return tool


@pytest.mark.asyncio
async def test_discover_registers_tools():
    mock_bridge = MagicMock()
    mock_bridge.add_tool = MagicMock()
    mock_tools = [
        _make_mock_tool(
            "search_plugins",
            "Search for plugins",
            {"properties": {"query": {"type": "string"}}, "required": ["query"]},
        ),
        _make_mock_tool(
            "list_loaded_plugins",
            "List loaded plugins",
            {"properties": {}, "required": []},
        ),
    ]
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.tools = mock_tools
    mock_session.list_tools = AsyncMock(return_value=mock_result)
    mock_session.initialize = AsyncMock()
    with patch("carla_mcp.tool_proxy.sse_client") as mock_sse:
        mock_sse.return_value.__aenter__ = AsyncMock(
            return_value=(AsyncMock(), AsyncMock())
        )
        with patch("carla_mcp.tool_proxy.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            count = await discover_and_register(
                mock_bridge, "http://localhost:3001/sse"
            )
    assert count == 2
    assert mock_bridge.add_tool.call_count == 2


@pytest.mark.asyncio
async def test_unregister_removes_all():
    mock_bridge = MagicMock()
    mock_bridge.remove_tool = MagicMock()
    _registered_tools.clear()
    _registered_tools.update({"search_plugins", "list_loaded_plugins"})
    unregister_all(mock_bridge)
    assert mock_bridge.remove_tool.call_count == 2
    assert len(_registered_tools) == 0


@pytest.mark.asyncio
async def test_discover_returns_zero_on_connection_error():
    mock_bridge = MagicMock()
    with patch("carla_mcp.tool_proxy.sse_client") as mock_sse:
        mock_sse.return_value.__aenter__ = AsyncMock(
            side_effect=ConnectionRefusedError()
        )
        count = await discover_and_register(
            mock_bridge, "http://localhost:3001/sse"
        )
    assert count == 0


@pytest.mark.asyncio
async def test_discover_registers_tools_with_prefix():
    """Tools registered via discover_and_register with a prefix get prefixed names."""
    mock_bridge = MagicMock()
    mock_bridge.add_tool = MagicMock()
    mock_tools = [
        _make_mock_tool(
            "search_plugins",
            "Search for plugins",
            {"properties": {"query": {"type": "string"}}, "required": ["query"]},
        ),
    ]
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.tools = mock_tools
    mock_session.list_tools = AsyncMock(return_value=mock_result)
    mock_session.initialize = AsyncMock()
    with patch("carla_mcp.tool_proxy.sse_client") as mock_sse:
        mock_sse.return_value.__aenter__ = AsyncMock(
            return_value=(AsyncMock(), AsyncMock())
        )
        with patch("carla_mcp.tool_proxy.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            count = await discover_and_register(
                mock_bridge, "http://localhost:3001/sse", prefix="carla"
            )
    assert count == 1
    # Verify the tool was registered with the prefixed name
    tool_obj = mock_bridge.add_tool.call_args[0][0]
    assert tool_obj.name == "carla_search_plugins"


@pytest.mark.asyncio
async def test_unregister_by_prefix():
    """unregister_all with a prefix only removes tools with that prefix."""
    mock_bridge = MagicMock()
    mock_bridge.remove_tool = MagicMock()
    _registered_tools.clear()
    _registered_tools.update({
        "carla_search_plugins", "carla_list_plugins",
        "looper_record", "looper_play",
    })
    removed = unregister_all(mock_bridge, prefix="carla")
    assert removed == 2
    assert _registered_tools == {"looper_record", "looper_play"}


@pytest.mark.asyncio
async def test_discover_clears_previous_on_rediscovery():
    mock_bridge = MagicMock()
    mock_bridge.add_tool = MagicMock()
    mock_bridge.remove_tool = MagicMock()
    _registered_tools.clear()
    _registered_tools.update({"old_tool_1", "old_tool_2"})
    mock_tools = [
        _make_mock_tool(
            "new_tool", "A new tool", {"properties": {}, "required": []}
        )
    ]
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.tools = mock_tools
    mock_session.list_tools = AsyncMock(return_value=mock_result)
    mock_session.initialize = AsyncMock()
    with patch("carla_mcp.tool_proxy.sse_client") as mock_sse:
        mock_sse.return_value.__aenter__ = AsyncMock(
            return_value=(AsyncMock(), AsyncMock())
        )
        with patch("carla_mcp.tool_proxy.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            unregister_all(mock_bridge)
            count = await discover_and_register(
                mock_bridge, "http://localhost:3001/sse"
            )
    assert mock_bridge.remove_tool.call_count == 2
    assert count == 1
    assert _registered_tools == {"new_tool"}
