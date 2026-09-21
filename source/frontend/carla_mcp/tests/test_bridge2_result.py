import asyncio

from carla_mcp.backends.rpc import RpcError
from carla_mcp.bridge.result import ToolError, fail, ok, tool_boundary


def test_ok_and_fail_shapes():
    assert ok({"a": 1}, notes=["n"]) == {"ok": True, "result": {"a": 1}, "error": None, "notes": ["n"]}
    assert fail("not_found", "x") == {"ok": False, "result": None,
                                      "error": {"type": "not_found", "message": "x"}, "notes": []}


def test_boundary_passes_dict_through_and_wraps_plain_values():
    @tool_boundary
    async def a():
        return ok(1)

    @tool_boundary
    async def b():
        return "plain"

    assert asyncio.run(a()) == ok(1)
    assert asyncio.run(b()) == ok("plain")


def test_boundary_maps_tool_error_and_rpc_error():
    @tool_boundary
    async def a():
        raise ToolError("validation", "bad arg", notes=["hint"])

    @tool_boundary
    async def b():
        raise RpcError("backend_unavailable", "carla down")

    assert asyncio.run(a()) == fail("validation", "bad arg", notes=["hint"])
    assert asyncio.run(b()) == fail("backend_unavailable", "carla down")


def test_boundary_maps_unexpected_exception_to_internal():
    @tool_boundary
    async def a():
        raise KeyError("oops")

    out = asyncio.run(a())
    assert out["ok"] is False and out["error"]["type"] == "internal" and "KeyError" in out["error"]["message"]


def test_boundary_preserves_name_and_signature():
    @tool_boundary
    async def rig_state(focus: str = None, detail: str = "normal") -> dict:
        """doc"""
        return ok(None)

    import inspect
    assert rig_state.__name__ == "rig_state" and rig_state.__doc__ == "doc"
    assert list(inspect.signature(rig_state).parameters) == ["focus", "detail"]
