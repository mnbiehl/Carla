"""Threaded TCP JSON-lines RPC server for the Carla worker (stdlib only).

One request per line, one reply per line, connections may stay open.  This
is the RPC boundary: it is one of the three places allowed to catch
Exception, because a bug in a host call must become an `internal` reply,
never a dead worker.
"""

from __future__ import annotations

import json
import logging
import socketserver
import threading
from typing import Any, Optional

from carla_mcp.worker.api import RpcError

log = logging.getLogger("carla_mcp.worker")


class RpcServer:
    def __init__(self, api: Any, host: str = "127.0.0.1", port: int = 0):
        self.api = api
        self.host = host
        self._port = port
        self._server: Optional[socketserver.ThreadingTCPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else self._port

    @staticmethod
    def encode_reply(req_id: Any, result: Any = None, error: Optional[dict] = None) -> bytes:
        body = {"id": req_id, "ok": error is None}
        if error is None:
            body["result"] = result
        else:
            body["error"] = error
        return json.dumps(body).encode() + b"\n"

    def handle_line(self, line: bytes) -> bytes:
        req_id = None
        try:
            req = json.loads(line.decode())
            if not isinstance(req, dict):
                raise ValueError("request must be an object")
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params") or {}
            if not isinstance(method, str) or not isinstance(params, dict):
                raise ValueError("request needs string 'method' and object 'params'")
        except (ValueError, UnicodeDecodeError) as exc:
            return self.encode_reply(req_id, error={"type": "validation", "message": str(exc)})
        try:
            return self.encode_reply(req_id, result=self.api.dispatch(method, params))
        except RpcError as exc:
            return self.encode_reply(req_id, error={"type": exc.type, "message": exc.message})
        except Exception as exc:  # noqa: BLE001 — RPC boundary
            log.exception("worker method %s failed", method)
            return self.encode_reply(req_id, error={"type": "internal",
                                                    "message": f"{type(exc).__name__}: {exc}"})

    def start(self) -> None:
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                for line in self.rfile:
                    if not line.strip():
                        continue
                    self.wfile.write(outer.handle_line(line))
                    self.wfile.flush()

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = Server((self.host, self._port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="carla-rpc-worker", daemon=True)
        self._thread.start()
        log.info("worker RPC listening on %s:%d", self.host, self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
