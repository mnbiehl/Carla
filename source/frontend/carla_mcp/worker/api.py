"""The allowlisted host API the worker exposes over RPC (stdlib only).

Every public method here is one RPC method. dispatch() is the only entry;
it refuses anything not in ALLOWLIST and validates parameters by name.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Optional

from carla_backend import BINARY_NATIVE

from carla_mcp.worker.patchbay import PatchbayCache

HANDLE_KEY = "mcp_handle"
HANDLE_TYPE = "string"

ALLOWLIST = frozenset({
    "ping", "version", "engine_info", "plugins", "plugin_info", "add_plugin",
    "remove_plugin", "set_active", "param_list", "param_get", "param_set",
    "custom_data_get", "custom_data_set", "audio_port_counts", "patchbay_refresh",
    "patchbay_list", "patchbay_connect", "patchbay_disconnect", "project_save",
    "project_load", "engine_stop",
})


class RpcError(Exception):
    def __init__(self, type: str, message: str):
        super().__init__(f"{type}: {message}")
        self.type = type
        self.message = message


class WorkerApi:
    def __init__(self, host: Any, cache: PatchbayCache, version: str = "dev",
                 client_name: str = "Carla",
                 on_engine_stop: Optional[Callable[[], None]] = None):
        self.host = host
        self.cache = cache
        self.version_str = version
        self.client_name = client_name
        self._on_engine_stop = on_engine_stop

    # ----- dispatch -----------------------------------------------------

    def dispatch(self, method: str, params: Dict[str, Any]) -> Any:
        if method not in ALLOWLIST:
            raise RpcError("validation", f"unknown method: {method}")
        fn = getattr(self, method)
        sig = inspect.signature(fn)
        try:
            bound = sig.bind(**(params or {}))
        except TypeError as exc:
            raise RpcError("validation", f"{method}: {exc}") from exc
        return fn(*bound.args, **bound.kwargs)

    # ----- helpers -------------------------------------------------------

    def _check_pid(self, plugin_id: int) -> int:
        count = self.host.get_current_plugin_count()
        if not isinstance(plugin_id, int) or not 0 <= plugin_id < count:
            raise RpcError("not_found", f"no plugin with id {plugin_id} (count={count})")
        return plugin_id

    def _require(self, ok: bool, what: str) -> None:
        if not ok:
            raise RpcError("internal", f"{what}: {self.host.get_last_error()}")

    def _handle(self, plugin_id: int) -> Optional[str]:
        value = self.host.get_custom_data_value(plugin_id, HANDLE_TYPE, HANDLE_KEY)
        return value or None

    # ----- engine --------------------------------------------------------

    def ping(self) -> str:
        return "pong"

    def version(self) -> dict:
        return {"worker": self.version_str}

    def engine_info(self) -> dict:
        return {
            "running": bool(self.host.is_engine_running()),
            "sample_rate": float(self.host.get_sample_rate()),
            "buffer_size": int(self.host.get_buffer_size()),
            "client_name": self.client_name,
        }

    def engine_stop(self) -> dict:
        if self._on_engine_stop is not None:
            self._on_engine_stop()
        return {"stopping": True}

    # ----- plugins -------------------------------------------------------

    def _plugin_entry(self, plugin_id: int) -> dict:
        info = self.host.get_plugin_info(plugin_id)
        return {
            "id": plugin_id,
            "name": info["name"],
            "label": info["label"],
            "filename": info["filename"],
            "type": info["type"],
            "unique_id": info.get("uniqueId", 0),
            "maker": info.get("maker", ""),
            "handle": self._handle(plugin_id),
        }

    def plugins(self) -> List[dict]:
        return [self._plugin_entry(pid) for pid in range(self.host.get_current_plugin_count())]

    def plugin_info(self, plugin_id: int) -> dict:
        return self._plugin_entry(self._check_pid(plugin_id))

    def add_plugin(self, ptype: int, path: str, label: str, name: str = "") -> dict:
        before = self.host.get_current_plugin_count()
        ok = self.host.add_plugin(BINARY_NATIVE, ptype, path, name, label, 0, None, 0)
        self._require(bool(ok), f"add_plugin {label}")
        after = self.host.get_current_plugin_count()
        if after <= before:
            raise RpcError("internal", f"add_plugin {label}: plugin count did not grow")
        return {"plugin_id": after - 1}

    def remove_plugin(self, plugin_id: int) -> dict:
        pid = self._check_pid(plugin_id)
        self._require(bool(self.host.remove_plugin(pid)), f"remove_plugin {pid}")
        return {"removed": pid}

    def set_active(self, plugin_id: int, active: bool) -> dict:
        pid = self._check_pid(plugin_id)
        self.host.set_active(pid, bool(active))
        return {"plugin_id": pid, "active": bool(active)}

    def audio_port_counts(self, plugin_id: int) -> dict:
        pid = self._check_pid(plugin_id)
        info = self.host.get_audio_port_count_info(pid)
        return {"ins": int(info["ins"]), "outs": int(info["outs"])}

    # ----- parameters ----------------------------------------------------

    def _param(self, pid: int, param_id: int) -> dict:
        info = self.host.get_parameter_info(pid, param_id)
        ranges = self.host.get_parameter_ranges(pid, param_id)
        return {
            "id": param_id,
            "name": info["name"],
            "symbol": info["symbol"],
            "unit": info["unit"],
            "min": float(ranges["min"]),
            "max": float(ranges["max"]),
            "default": float(ranges["def"]),
            "step": float(ranges["step"]),
            "value": float(self.host.get_current_parameter_value(pid, param_id)),
        }

    def _check_param(self, pid: int, param_id: int) -> int:
        count = self.host.get_parameter_count(pid)
        if not isinstance(param_id, int) or not 0 <= param_id < count:
            raise RpcError("not_found", f"plugin {pid} has no parameter {param_id} (count={count})")
        return param_id

    def param_list(self, plugin_id: int) -> List[dict]:
        pid = self._check_pid(plugin_id)
        return [self._param(pid, i) for i in range(self.host.get_parameter_count(pid))]

    def param_get(self, plugin_id: int, param_id: int) -> dict:
        pid = self._check_pid(plugin_id)
        return self._param(pid, self._check_param(pid, param_id))

    def param_set(self, plugin_id: int, param_id: int, value: float) -> dict:
        pid = self._check_pid(plugin_id)
        prm = self._check_param(pid, param_id)
        self.host.set_parameter_value(pid, prm, float(value))
        return {"plugin_id": pid, "param_id": prm, "value": float(value)}

    # ----- custom data ---------------------------------------------------

    def custom_data_get(self, plugin_id: int, key: str) -> dict:
        pid = self._check_pid(plugin_id)
        return {"key": key, "value": self.host.get_custom_data_value(pid, HANDLE_TYPE, key) or None}

    def custom_data_set(self, plugin_id: int, key: str, value: str) -> dict:
        pid = self._check_pid(plugin_id)
        self._require(bool(self.host.set_custom_data(pid, HANDLE_TYPE, key, value)),
                      f"set_custom_data {key}")
        return {"key": key, "value": value}

    # ----- patchbay ------------------------------------------------------

    def patchbay_refresh(self) -> dict:
        self.cache.clear()
        self._require(bool(self.host.patchbay_refresh(False)), "patchbay_refresh")
        return {"refreshed": True}

    def patchbay_list(self) -> dict:
        return self.cache.snapshot()

    def patchbay_connect(self, group_out: int, port_out: int, group_in: int, port_in: int) -> dict:
        ok = self.host.patchbay_connect(False, group_out, port_out, group_in, port_in)
        self._require(bool(ok), f"patchbay_connect {group_out}:{port_out}->{group_in}:{port_in}")
        return {"connected": True}

    def patchbay_disconnect(self, connection_id: int) -> dict:
        self._require(bool(self.host.patchbay_disconnect(False, connection_id)),
                      f"patchbay_disconnect {connection_id}")
        return {"disconnected": connection_id}

    # ----- project -------------------------------------------------------

    def project_save(self, path: str) -> dict:
        self._require(bool(self.host.save_project(path)), f"save_project {path}")
        return {"path": path}

    def project_load(self, path: str) -> dict:
        self._require(bool(self.host.load_project(path)), f"load_project {path}")
        return {"path": path}
