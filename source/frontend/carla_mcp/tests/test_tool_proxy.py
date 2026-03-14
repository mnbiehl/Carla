import pytest
from carla_mcp.tool_proxy import _json_schema_type


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
