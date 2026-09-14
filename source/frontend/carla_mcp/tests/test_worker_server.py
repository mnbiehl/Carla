import json
import socket

from carla_mcp.worker.api import RpcError
from carla_mcp.worker.server import RpcServer


class FakeApi:
    def dispatch(self, method, params):
        if method == "ping":
            return "pong"
        if method == "echo":
            return params
        if method == "boom":
            raise RuntimeError("kaboom")
        raise RpcError("validation", f"unknown method: {method}")


def _roundtrip(port, *lines):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
        f = s.makefile("rwb")
        out = []
        for line in lines:
            f.write(line.encode() + b"\n")
            f.flush()
            out.append(json.loads(f.readline()))
        return out


def test_handles_requests_over_one_connection():
    srv = RpcServer(FakeApi(), port=0)
    srv.start()
    try:
        replies = _roundtrip(srv.port,
                             json.dumps({"id": 1, "method": "ping", "params": {}}),
                             json.dumps({"id": 2, "method": "echo", "params": {"a": 1}}))
    finally:
        srv.stop()
    assert replies == [{"id": 1, "ok": True, "result": "pong"},
                       {"id": 2, "ok": True, "result": {"a": 1}}]


def test_typed_error_and_internal_error_envelopes():
    srv = RpcServer(FakeApi(), port=0)
    srv.start()
    try:
        replies = _roundtrip(srv.port,
                             json.dumps({"id": 3, "method": "nope", "params": {}}),
                             json.dumps({"id": 4, "method": "boom", "params": {}}))
    finally:
        srv.stop()
    assert replies[0] == {"id": 3, "ok": False, "error": {"type": "validation", "message": "unknown method: nope"}}
    assert replies[1]["ok"] is False and replies[1]["error"]["type"] == "internal"
    assert "kaboom" in replies[1]["error"]["message"]


def test_bad_json_is_validation_error_with_null_id():
    srv = RpcServer(FakeApi(), port=0)
    srv.start()
    try:
        replies = _roundtrip(srv.port, "{not json")
    finally:
        srv.stop()
    assert replies[0]["id"] is None and replies[0]["error"]["type"] == "validation"


def test_handle_line_is_pure():
    srv = RpcServer(FakeApi(), port=0)
    out = json.loads(srv.handle_line(b'{"id": 9, "method": "ping", "params": {}}'))
    assert out == {"id": 9, "ok": True, "result": "pong"}
