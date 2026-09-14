import asyncio
from unittest.mock import AsyncMock

import pytest

from carla_mcp.backends.looper import LooperClient
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
    t.request.assert_awaited_with('"GetState"')
    assert asyncio.run(client.loopers()) == [
        {"id": 7, "name": "uke", "port_index": 0, "mode": "Playing", "level_db": -3.0, "pan": 0.0, "input_source": None}
    ]


def test_set_level_db_sends_db_not_percent():
    client, t = _client({"ok": True})
    asyncio.run(client.set_level_db(7, -6.0))
    t.request.assert_awaited_with('{"Looper": [{"SetLevel": -6.0}, {"Id": 7}]}')


def test_session_and_mute_commands():
    client, t = _client({"ok": True})
    asyncio.run(client.save_session_at("/tmp/s"))
    t.request.assert_awaited_with('{"SaveSessionAt": "/tmp/s"}')
    asyncio.run(client.load_session("/tmp/s/project.loopers"))
    t.request.assert_awaited_with('{"LoadSession": "/tmp/s/project.loopers"}')
    asyncio.run(client.set_main_mute(True))
    t.request.assert_awaited_with('{"SetMainOutputMute": true}')
    asyncio.run(client.set_all_mute(False))
    t.request.assert_awaited_with('{"SetAllOutputsMute": false}')


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
