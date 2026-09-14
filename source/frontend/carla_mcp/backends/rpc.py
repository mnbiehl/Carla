"""JSON-lines RPC transport — the ONLY place backend exceptions are caught.

One TCP connection per request (both the Carla worker and the loopers engine
accept that), so there is nothing to reconnect.  CarlaRpc adds the
{id, method, params} / {id, ok, result|error} envelope; the loopers adapter
in backends/looper.py uses the bare transport.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any, Optional

# asyncio's default StreamReader limit is 64 KiB; phase-2 replies (param_list on
# large LV2 plugins, patchbay_list) exceed it. One reply line may be this long.
RPC_READ_LIMIT_BYTES = 16 * 1024 * 1024


class RpcError(Exception):
    """A typed backend failure. type ∈ not_found|validation|backend_unavailable|internal."""

    def __init__(self, type: str, message: str):
        super().__init__(f"{type}: {message}")
        self.type = type
        self.message = message


class JsonLinesTransport:
    def __init__(self, host: str = "127.0.0.1", port: int = 0, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    async def request(self, payload: str, timeout: Optional[float] = None) -> dict:
        """Send one line, read one line, parse JSON. Raises RpcError only.

        `timeout`, when given, overrides the transport default for this
        call's read only; the connect timeout stays `self.timeout`.
        """
        read_timeout = self.timeout if timeout is None else timeout
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, limit=RPC_READ_LIMIT_BYTES),
                self.timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise RpcError("backend_unavailable",
                           f"cannot connect to {self.host}:{self.port}: {exc}") from exc
        try:
            writer.write(payload.encode() + b"\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), read_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise RpcError("backend_unavailable",
                           f"request to {self.host}:{self.port} failed: {exc}") from exc
        except (ValueError, asyncio.LimitOverrunError) as exc:
            # StreamReader.readline raises ValueError when one line overruns the limit.
            raise RpcError("internal", f"reply exceeds {RPC_READ_LIMIT_BYTES} bytes") from exc
        finally:
            writer.close()
        if not line:
            raise RpcError("internal", "empty reply")
        try:
            reply = json.loads(line.decode())
        except (ValueError, UnicodeDecodeError) as exc:
            raise RpcError("internal", f"unparseable reply: {line[:80]!r}") from exc
        if not isinstance(reply, dict):
            raise RpcError("internal", f"reply is not an object: {reply!r}")
        return reply

    async def reachable(self) -> bool:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), 1.0
            )
        except (OSError, asyncio.TimeoutError):
            return False
        writer.close()
        return True


class CarlaRpc:
    """{id, method, params} → {id, ok, result | error} over a JsonLinesTransport."""

    def __init__(self, transport: JsonLinesTransport):
        self.transport = transport
        self._ids = itertools.count(1)

    async def call(self, method: str, params: Optional[dict] = None,
                    timeout: Optional[float] = None) -> Any:
        req_id = next(self._ids)
        payload = json.dumps({"id": req_id, "method": method, "params": params or {}})
        reply = await self.transport.request(payload, timeout=timeout)
        if reply.get("id") != req_id:
            raise RpcError("internal", f"reply id {reply.get('id')} != request id {req_id}")
        if reply.get("ok"):
            return reply.get("result")
        error = reply.get("error") or {}
        raise RpcError(str(error.get("type", "internal")), str(error.get("message", "unknown error")))
