import inspect
import pytest
from carla_mcp.tool_proxy import _json_schema_type, _build_tool_function


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
