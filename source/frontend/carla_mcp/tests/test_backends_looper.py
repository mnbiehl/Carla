import asyncio
from unittest.mock import AsyncMock

import pytest

from carla_mcp.backends.looper import LONG_OP_TIMEOUT_S, LooperClient
from carla_mcp.backends.rpc import RpcError


def _client(reply):
    t = AsyncMock()
    t.request = AsyncMock(return_value=reply)
    return LooperClient(t), t


def test_get_state_unwraps_envelope_and_loopers_table():
    state = {"state": {"main_muted": False, "loopers": [
        {"id": 7, "name": "uke", "port_index": 0, "mode": "Playing", "level_db": -3.0, "pan": 0.0, "input_source": None},
    ]}}
    client, t = _client(state)
    assert asyncio.run(client.get_state())["main_muted"] is False
    t.request.assert_awaited_with('"GetState"', timeout=None)
    assert asyncio.run(client.loopers()) == [
        {"id": 7, "name": "uke", "port_index": 0, "mode": "Playing", "level_db": -3.0, "pan": 0.0, "input_source": None}
    ]


def test_set_level_db_sends_db_not_percent():
    client, t = _client({"ok": True})
    asyncio.run(client.set_level_db(7, -6.0))
    t.request.assert_awaited_with('{"Looper": [{"SetLevel": -6.0}, {"Id": 7}]}', timeout=None)


def test_session_and_mute_commands():
    client, t = _client({"ok": True})
    asyncio.run(client.save_session_at("/tmp/s"))
    t.request.assert_awaited_with('{"SaveSessionAt": "/tmp/s"}', timeout=LONG_OP_TIMEOUT_S)
    asyncio.run(client.load_session("/tmp/s/project.loopers"))
    t.request.assert_awaited_with('{"LoadSession": "/tmp/s/project.loopers"}', timeout=LONG_OP_TIMEOUT_S)
    asyncio.run(client.set_main_mute(True))
    t.request.assert_awaited_with('{"SetMainOutputMute": true}', timeout=None)
    asyncio.run(client.set_all_mute(False))
    t.request.assert_awaited_with('{"SetAllOutputsMute": false}', timeout=None)


def test_load_and_save_session_use_long_timeout():
    client, t = _client({"ok": True})
    asyncio.run(client.load_session("/tmp/s/project.loopers"))
    assert t.request.call_args.kwargs["timeout"] == LONG_OP_TIMEOUT_S
    t.request.reset_mock()
    asyncio.run(client.save_session_at("/tmp/s"))
    assert t.request.call_args.kwargs["timeout"] == LONG_OP_TIMEOUT_S


def test_normal_command_does_not_override_timeout():
    client, t = _client({"ok": True})
    asyncio.run(client.set_main_mute(True))
    assert t.request.call_args.kwargs["timeout"] is None


def test_engine_error_raises_rpc_error():
    client, _ = _client({"error": "no such looper"})
    with pytest.raises(RpcError) as exc:
        asyncio.run(client.set_pan(9, 0.5))
    assert exc.value.type == "internal" and "no such looper" in exc.value.message


def test_get_state_raises_when_state_envelope_missing():
    client, _ = _client({"ok": True})
    with pytest.raises(RpcError) as exc:
        asyncio.run(client.get_state())
    assert exc.value.type == "internal"
    assert "state" in exc.value.message


def test_loopers_skips_entries_without_port_index():
    client, _ = _client({"state": {"loopers": [{"id": 1}, {"id": 2, "port_index": 1}]}})
    assert [l["id"] for l in asyncio.run(client.loopers())] == [2]
