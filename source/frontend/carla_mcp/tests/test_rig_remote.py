"""Tests for RemoteInstance (rig/remote.py)."""

import asyncio
import json
import pytest
from carla_mcp.rig.remote import RemoteInstance, RemoteError


# ---------------------------------------------------------------------------
# Test helpers


class FakeCallTool:
    """Fake async call_tool that records calls and returns a canned response."""

    def __init__(self, canned: str = "OK") -> None:
        self.calls: list[tuple[str, dict]] = []
        self._canned = canned

    def with_response(self, canned: str) -> "FakeCallTool":
        self._canned = canned
        return self

    async def __call__(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, args))
        return self._canned


def make_remote(canned: str = "OK") -> tuple[RemoteInstance, FakeCallTool]:
    fake = FakeCallTool(canned)
    return RemoteInstance(fake), fake


# ---------------------------------------------------------------------------
# call() passthrough


def test_call_forwards_tool_name_and_kwargs():
    remote, fake = make_remote("result")

    async def _run():
        return await remote.call("my_tool", x=1, y="hello")

    result = asyncio.run(_run())
    assert result == "result"
    assert len(fake.calls) == 1
    name, args = fake.calls[0]
    assert name == "my_tool"
    assert args == {"x": 1, "y": "hello"}


# ---------------------------------------------------------------------------
# add_plugin


def test_add_plugin_forwards_correct_tool_and_args():
    remote, fake = make_remote("✅ added")

    asyncio.run(remote.add_plugin("MyComp"))

    assert len(fake.calls) == 1
    name, args = fake.calls[0]
    assert name == "add_plugin_by_name"
    assert args["plugin_name"] == "MyComp"
    assert "plugin_type" not in args


def test_add_plugin_includes_type_when_given():
    remote, fake = make_remote()

    asyncio.run(remote.add_plugin("MyComp", plugin_type="lv2"))

    name, args = fake.calls[0]
    assert name == "add_plugin_by_name"
    assert args["plugin_type"] == "lv2"


# ---------------------------------------------------------------------------
# remove_plugin


def test_remove_plugin_forwards_correct_tool_and_args():
    remote, fake = make_remote("✅ removed")

    asyncio.run(remote.remove_plugin(3))

    name, args = fake.calls[0]
    assert name == "remove_plugin"
    assert args == {"plugin_id": 3}


# ---------------------------------------------------------------------------
# set_parameter


def test_set_parameter_forwards_correct_tool_and_args():
    remote, fake = make_remote("✅ set")

    asyncio.run(remote.set_parameter(2, 7, 0.5))

    name, args = fake.calls[0]
    assert name == "set_plugin_parameter"
    assert args == {"plugin_id": 2, "parameter_id": 7, "value": 0.5}


# ---------------------------------------------------------------------------
# set_handle


def test_set_handle_forwards_correct_tool_and_args():
    remote, fake = make_remote("✅ handle set")

    asyncio.run(remote.set_handle(1, "strat/comp"))

    name, args = fake.calls[0]
    assert name == "set_plugin_handle"
    assert args == {"plugin_id": 1, "handle": "strat/comp"}


# ---------------------------------------------------------------------------
# list_handles


def test_list_handles_parses_json_response():
    payload = json.dumps({"0": "strat/comp", "1": "strat/amp"})
    remote, fake = make_remote(payload)

    result = asyncio.run(remote.list_handles())

    assert result == {0: "strat/comp", 1: "strat/amp"}


def test_list_handles_returns_empty_dict_on_invalid_json():
    remote, fake = make_remote("not-json")

    result = asyncio.run(remote.list_handles())

    assert result == {}


def test_list_handles_calls_list_plugin_handles_tool():
    payload = json.dumps({"0": "h"})
    remote, fake = make_remote(payload)

    asyncio.run(remote.list_handles())

    name, args = fake.calls[0]
    assert name == "list_plugin_handles"
    assert args == {}


# ---------------------------------------------------------------------------
# resolve_handle


def test_resolve_handle_returns_matching_id():
    payload = json.dumps({"0": "strat/comp", "1": "strat/amp"})
    remote, fake = make_remote(payload)

    result = asyncio.run(remote.resolve_handle("strat/amp"))

    assert result == 1


def test_resolve_handle_returns_none_when_absent():
    payload = json.dumps({"0": "strat/comp"})
    remote, fake = make_remote(payload)

    result = asyncio.run(remote.resolve_handle("does/not/exist"))

    assert result is None


def test_resolve_handle_makes_exactly_one_call():
    payload = json.dumps({"0": "strat/comp", "1": "strat/amp"})
    remote, fake = make_remote(payload)

    asyncio.run(remote.resolve_handle("strat/comp"))

    assert len(fake.calls) == 1
    assert fake.calls[0][0] == "list_plugin_handles"


# ---------------------------------------------------------------------------
# Transport errors (M5): a comms failure must raise, not look like empty data


def test_list_handles_propagates_remote_error():
    async def boom(tool_name, args):
        raise RemoteError("transport down")

    remote = RemoteInstance(boom)
    with pytest.raises(RemoteError):
        asyncio.run(remote.list_handles())


def test_get_parameters_propagates_remote_error():
    async def boom(tool_name, args):
        raise RemoteError("transport down")

    remote = RemoteInstance(boom)
    with pytest.raises(RemoteError):
        asyncio.run(remote.get_parameters(0))


def test_over_sse_raises_remote_error_on_transport_failure(monkeypatch):
    import carla_mcp.rig.remote as remote_mod

    def boom(url):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(remote_mod, "sse_client", boom)
    remote = RemoteInstance.over_sse("http://127.0.0.1:9999/sse")
    with pytest.raises(RemoteError):
        asyncio.run(remote.call("anything"))


def test_over_sse_times_out_to_remote_error(monkeypatch):
    import carla_mcp.rig.remote as remote_mod

    class _HangingCM:
        async def __aenter__(self):
            await asyncio.sleep(10)

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(remote_mod, "sse_client", lambda url: _HangingCM())
    remote = RemoteInstance.over_sse("http://127.0.0.1:9999/sse", timeout=0.05)
    with pytest.raises(RemoteError):
        asyncio.run(remote.call("anything"))
