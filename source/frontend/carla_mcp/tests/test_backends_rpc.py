import asyncio
import json

import pytest

from carla_mcp.backends.rpc import CarlaRpc, JsonLinesTransport, RpcError


async def _serve(handler):
    """Start a JSON-lines server on an ephemeral port; handler(dict)->dict|str."""
    async def on_conn(reader, writer):
        line = await reader.readline()
        req = json.loads(line)
        rep = handler(req)
        writer.write((json.dumps(rep) if not isinstance(rep, str) else rep).encode() + b"\n")
        await writer.drain()
        writer.close()
    server = await asyncio.start_server(on_conn, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def test_call_returns_result_and_echoes_id():
    async def run():
        seen = {}
        def handler(req):
            seen.update(req)
            return {"id": req["id"], "ok": True, "result": {"pong": 1}}
        server, port = await _serve(handler)
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port))
        result = await rpc.call("ping", {})
        server.close()
        return seen, result
    seen, result = asyncio.run(run())
    assert seen["method"] == "ping" and seen["params"] == {} and isinstance(seen["id"], int)
    assert result == {"pong": 1}


def test_error_envelope_raises_typed_rpc_error():
    async def run():
        server, port = await _serve(lambda r: {"id": r["id"], "ok": False,
                                              "error": {"type": "not_found", "message": "no plugin 9"}})
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port))
        with pytest.raises(RpcError) as exc:
            await rpc.call("plugin_info", {"plugin_id": 9})
        server.close()
        return exc.value
    err = asyncio.run(run())
    assert err.type == "not_found" and "no plugin 9" in err.message


def test_connection_refused_is_backend_unavailable():
    async def run():
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", 1))  # nothing listens on port 1
        with pytest.raises(RpcError) as exc:
            await rpc.call("ping")
        return exc.value
    assert asyncio.run(run()).type == "backend_unavailable"


def test_garbage_reply_is_internal():
    async def run():
        server, port = await _serve(lambda r: "this is not json")
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port))
        with pytest.raises(RpcError) as exc:
            await rpc.call("ping")
        server.close()
        return exc.value
    assert asyncio.run(run()).type == "internal"


def test_reachable_probe():
    async def run():
        server, port = await _serve(lambda r: {"id": r["id"], "ok": True, "result": None})
        up = await JsonLinesTransport("127.0.0.1", port).reachable()
        server.close()
        down = await JsonLinesTransport("127.0.0.1", 1).reachable()
        return up, down
    assert asyncio.run(run()) == (True, False)


def test_connect_timeout_is_backend_unavailable(monkeypatch):
    async def never_connects(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(asyncio, "open_connection", never_connects)

    async def run():
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", 9, timeout=0.05))
        with pytest.raises(RpcError) as exc:
            await rpc.call("ping")
        return exc.value

    assert asyncio.run(run()).type == "backend_unavailable"


def test_read_timeout_is_backend_unavailable():
    async def run():
        async def on_conn(reader, writer):
            await reader.readline()
            await asyncio.sleep(1)  # never reply
        server = await asyncio.start_server(on_conn, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port, timeout=0.05))
        with pytest.raises(RpcError) as exc:
            await rpc.call("ping")
        server.close()
        return exc.value

    assert asyncio.run(run()).type == "backend_unavailable"


def test_empty_reply_is_internal():
    async def run():
        async def on_conn(reader, writer):
            await reader.readline()
            writer.close()  # hang up without replying
        server = await asyncio.start_server(on_conn, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port))
        with pytest.raises(RpcError) as exc:
            await rpc.call("ping")
        server.close()
        return exc.value

    err = asyncio.run(run())
    assert err.type == "internal" and "empty" in err.message


def test_reply_id_mismatch_is_internal():
    async def run():
        server, port = await _serve(lambda r: {"id": r["id"] + 1, "ok": True, "result": None})
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port))
        with pytest.raises(RpcError) as exc:
            await rpc.call("ping")
        server.close()
        return exc.value

    err = asyncio.run(run())
    assert err.type == "internal" and "id" in err.message


def test_call_timeout_override_replaces_read_timeout_only(monkeypatch):
    seen = {}
    real_wait_for = asyncio.wait_for

    async def spying_wait_for(aw, timeout):
        seen.setdefault("timeouts", []).append(timeout)
        return await real_wait_for(aw, timeout)

    async def run():
        server, port = await _serve(lambda r: {"id": r["id"], "ok": True, "result": None})
        monkeypatch.setattr(asyncio, "wait_for", spying_wait_for)
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port, timeout=5.0))
        await rpc.call("project_load", {"path": "/p"}, timeout=120.0)
        server.close()

    asyncio.run(run())
    # connect uses the transport default (5.0); the read uses the override (120.0).
    assert seen["timeouts"] == [5.0, 120.0]


def test_call_without_timeout_override_uses_transport_default(monkeypatch):
    seen = {}
    real_wait_for = asyncio.wait_for

    async def spying_wait_for(aw, timeout):
        seen.setdefault("timeouts", []).append(timeout)
        return await real_wait_for(aw, timeout)

    async def run():
        server, port = await _serve(lambda r: {"id": r["id"], "ok": True, "result": None})
        monkeypatch.setattr(asyncio, "wait_for", spying_wait_for)
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port, timeout=5.0))
        await rpc.call("ping")
        server.close()

    asyncio.run(run())
    assert seen["timeouts"] == [5.0, 5.0]


def test_non_object_reply_is_internal():
    async def run():
        server, port = await _serve(lambda r: "[1, 2]")
        rpc = CarlaRpc(JsonLinesTransport("127.0.0.1", port))
        with pytest.raises(RpcError) as exc:
            await rpc.call("ping")
        server.close()
        return exc.value

    err = asyncio.run(run())
    assert err.type == "internal" and "not an object" in err.message
