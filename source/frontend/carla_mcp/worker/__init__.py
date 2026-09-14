"""Thin RPC worker that runs inside a Carla process (GUI or headless).

Stdlib + carla_backend only.  See worker/api.py for the allowlist.
"""

from __future__ import annotations

from typing import Any

from carla_mcp.worker import events
from carla_mcp.worker.api import WorkerApi
from carla_mcp.worker.patchbay import PatchbayCache
from carla_mcp.worker.server import RpcServer

__all__ = ["attach", "detach", "events", "WorkerApi", "PatchbayCache", "RpcServer"]


def attach(host: Any, port: int, client_name: str = "Carla", version: str = "dev",
           on_engine_stop=None) -> RpcServer:
    """Start an RPC server over *host* and route engine callbacks into its cache."""
    cache = PatchbayCache()
    api = WorkerApi(host, cache, version=version, client_name=client_name,
                    on_engine_stop=on_engine_stop)
    server = RpcServer(api, port=port)
    events.register(cache)
    server.start()
    return server


def detach(server: RpcServer) -> None:
    events.register(None)
    server.stop()
