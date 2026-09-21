"""Patchbay state rebuilt from Carla engine callbacks (stdlib only)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List

from carla_backend import (
    ENGINE_CALLBACK_PATCHBAY_CLIENT_ADDED,
    ENGINE_CALLBACK_PATCHBAY_CLIENT_REMOVED,
    ENGINE_CALLBACK_PATCHBAY_CLIENT_RENAMED,
    ENGINE_CALLBACK_PATCHBAY_CONNECTION_ADDED,
    ENGINE_CALLBACK_PATCHBAY_CONNECTION_REMOVED,
    ENGINE_CALLBACK_PATCHBAY_PORT_ADDED,
    ENGINE_CALLBACK_PATCHBAY_PORT_REMOVED,
    PATCHBAY_PORT_IS_INPUT,
)


@dataclass
class _Group:
    id: int
    name: str
    plugin_id: int
    ports: Dict[int, dict] = field(default_factory=dict)


class PatchbayCache:
    """Groups, ports and connections as last reported by the engine."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._groups: Dict[int, _Group] = {}
        self._connections: Dict[int, dict] = {}

    def clear(self) -> None:
        with self._lock:
            self._groups.clear()
            self._connections.clear()

    def on_event(self, action: int, plugin_id: int, value1: int, value2: int,
                 value3: int, valuef: float, value_str: str) -> None:
        with self._lock:
            if action == ENGINE_CALLBACK_PATCHBAY_CLIENT_ADDED:
                self._groups[plugin_id] = _Group(id=plugin_id, name=value_str, plugin_id=value2)
            elif action == ENGINE_CALLBACK_PATCHBAY_CLIENT_REMOVED:
                self._groups.pop(plugin_id, None)
            elif action == ENGINE_CALLBACK_PATCHBAY_CLIENT_RENAMED:
                if plugin_id in self._groups:
                    self._groups[plugin_id].name = value_str
            elif action == ENGINE_CALLBACK_PATCHBAY_PORT_ADDED:
                group = self._groups.get(plugin_id)
                if group is not None:
                    group.ports[value1] = {
                        "id": value1, "name": value_str,
                        "input": bool(value2 & PATCHBAY_PORT_IS_INPUT),
                    }
            elif action == ENGINE_CALLBACK_PATCHBAY_PORT_REMOVED:
                group = self._groups.get(plugin_id)
                if group is not None:
                    group.ports.pop(value1, None)
            elif action == ENGINE_CALLBACK_PATCHBAY_CONNECTION_ADDED:
                parts = value_str.split(":")
                if len(parts) == 4 and all(p.lstrip("-").isdigit() for p in parts):
                    g_out, p_out, g_in, p_in = (int(p) for p in parts)
                    self._connections[plugin_id] = {
                        "id": plugin_id, "group_out": g_out, "port_out": p_out,
                        "group_in": g_in, "port_in": p_in,
                    }
            elif action == ENGINE_CALLBACK_PATCHBAY_CONNECTION_REMOVED:
                self._connections.pop(plugin_id, None)

    def snapshot(self) -> dict:
        with self._lock:
            groups: List[dict] = [
                {"id": g.id, "name": g.name, "plugin_id": g.plugin_id,
                 "ports": [g.ports[k] for k in sorted(g.ports)]}
                for g in (self._groups[k] for k in sorted(self._groups))
            ]
            connections = [self._connections[k] for k in sorted(self._connections)]
        return {"groups": groups, "connections": connections}
