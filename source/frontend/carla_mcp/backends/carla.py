"""Typed async client over the worker allowlist.

Each method name and its parameter names match worker/api.py exactly; the
contract test pins the two sets together.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from carla_mcp.backends.rpc import CarlaRpc

LONG_OP_TIMEOUT_S = 120.0


def _rpc(fn):
    """Mark an async method as an RPC method: its name is sent as the method,
    its keyword arguments as params."""

    async def wrapper(self, **params):
        return await self.rpc.call(fn.__name__, params)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.is_rpc = True
    return wrapper


def _rpc_long(fn):
    """Same as `_rpc`, but the call gets LONG_OP_TIMEOUT_S instead of the
    transport default, for verbs whose backend work (project load/save) can
    plausibly run past the default read timeout."""

    async def wrapper(self, **params):
        return await self.rpc.call(fn.__name__, params, timeout=LONG_OP_TIMEOUT_S)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.is_rpc = True
    return wrapper


class CarlaClient:
    def __init__(self, rpc: CarlaRpc):
        self.rpc = rpc

    @classmethod
    def rpc_methods(cls) -> frozenset:
        return frozenset(name for name, v in vars(cls).items() if getattr(v, "is_rpc", False))

    # engine
    @_rpc
    async def ping(self) -> str: ...
    @_rpc
    async def version(self) -> dict: ...
    @_rpc
    async def engine_info(self) -> dict: ...
    @_rpc
    async def engine_stop(self) -> dict: ...

    # plugins
    @_rpc
    async def plugins(self) -> List[dict]: ...
    @_rpc
    async def plugin_info(self, *, plugin_id: int) -> dict: ...
    @_rpc
    async def add_plugin(self, *, ptype: int, path: str, label: str, name: str = "") -> dict: ...
    @_rpc
    async def remove_plugin(self, *, plugin_id: int) -> dict: ...
    @_rpc
    async def set_active(self, *, plugin_id: int, active: bool) -> dict: ...
    @_rpc
    async def audio_port_counts(self, *, plugin_id: int) -> dict: ...

    # parameters
    @_rpc
    async def param_list(self, *, plugin_id: int) -> List[dict]: ...
    @_rpc
    async def param_get(self, *, plugin_id: int, param_id: int) -> dict: ...
    @_rpc
    async def param_set(self, *, plugin_id: int, param_id: int, value: float) -> dict: ...

    # custom data
    @_rpc
    async def custom_data_get(self, *, plugin_id: int, key: str) -> dict: ...
    @_rpc
    async def custom_data_set(self, *, plugin_id: int, key: str, value: str) -> dict: ...

    # patchbay
    @_rpc
    async def patchbay_refresh(self) -> dict: ...
    @_rpc
    async def patchbay_list(self) -> dict: ...
    @_rpc
    async def patchbay_connect(self, *, group_out: int, port_out: int, group_in: int, port_in: int) -> dict: ...
    @_rpc
    async def patchbay_disconnect(self, *, connection_id: int) -> dict: ...

    # project
    @_rpc_long
    async def project_save(self, *, path: str) -> dict: ...
    @_rpc_long
    async def project_load(self, *, path: str) -> dict: ...

    # convenience (not an RPC method)
    async def handles(self) -> Dict[str, int]:
        """handle → current plugin id, from the plugins() listing."""
        return {p["handle"]: p["id"] for p in await self.plugins() if p.get("handle")}
