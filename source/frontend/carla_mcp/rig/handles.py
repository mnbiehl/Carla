"""
Stable handle layer over Carla custom-data.

Plugin IDs in Carla are volatile — they shift whenever plugins are
added or removed.  This module stamps a stable string handle into each
plugin's Carla custom-data and resolves handles back to their current
plugin-id by scanning the live plugin list.

The host object passed to every function must expose:
    set_custom_data(plugin_id: int, type_: str, key: str, value: str) -> bool
    get_custom_data_value(plugin_id: int, type_: str, key: str) -> Optional[str]
    get_current_plugin_count() -> int
"""

from __future__ import annotations

from typing import Optional

HANDLE_KEY = "mcp_handle"
_HANDLE_TYPE = "string"


def stamp_handle(host: object, plugin_id: int, handle: str) -> bool:
    """Write *handle* into the plugin's Carla custom-data.

    Args:
        host:      A host-like object exposing set_custom_data.
        plugin_id: The current (volatile) Carla plugin-id.
        handle:    The stable handle to persist, e.g. "strat/comp".

    Returns:
        True if the custom-data was written successfully.
    """
    return host.set_custom_data(plugin_id, _HANDLE_TYPE, HANDLE_KEY, handle)


def resolve_handle(host: object, handle: str) -> Optional[int]:
    """Scan the live plugin list to find the plugin-id that carries *handle*.

    Args:
        host:   A host-like object exposing get_current_plugin_count and
                get_custom_data_value.
        handle: The stable handle to look up, e.g. "strat/comp".

    Returns:
        The current plugin-id (int) if found, otherwise None.
    """
    count = host.get_current_plugin_count()
    for pid in range(count):
        value = host.get_custom_data_value(pid, _HANDLE_TYPE, HANDLE_KEY)
        if value == handle:
            return pid
    return None


def read_handle(host: object, plugin_id: int) -> Optional[str]:
    """Return the handle stamped on *plugin_id*, or None if absent.

    Args:
        host:      A host-like object exposing get_custom_data_value.
        plugin_id: The current (volatile) Carla plugin-id.

    Returns:
        The handle string if stamped, otherwise None.
    """
    return host.get_custom_data_value(plugin_id, _HANDLE_TYPE, HANDLE_KEY)
