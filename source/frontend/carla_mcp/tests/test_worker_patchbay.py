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

from carla_mcp.worker import events
from carla_mcp.worker.patchbay import PatchbayCache


def _populate(cache):
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_CLIENT_ADDED, 10, 0, 3, 0, 0.0, "LSP Comp")
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_PORT_ADDED, 10, 1, PATCHBAY_PORT_IS_INPUT, 0, 0.0, "in_l")
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_PORT_ADDED, 10, 2, 0, 0, 0.0, "out_l")
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_CLIENT_ADDED, 11, 0, 4, 0, 0.0, "Reverb")
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_PORT_ADDED, 11, 1, PATCHBAY_PORT_IS_INPUT, 0, 0.0, "in_l")
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_CONNECTION_ADDED, 77, 0, 0, 0, 0.0, "10:2:11:1")


def test_snapshot_groups_ports_connections():
    cache = PatchbayCache()
    _populate(cache)
    snap = cache.snapshot()
    assert snap["groups"] == [
        {"id": 10, "name": "LSP Comp", "plugin_id": 3,
         "ports": [{"id": 1, "name": "in_l", "input": True}, {"id": 2, "name": "out_l", "input": False}]},
        {"id": 11, "name": "Reverb", "plugin_id": 4,
         "ports": [{"id": 1, "name": "in_l", "input": True}]},
    ]
    assert snap["connections"] == [
        {"id": 77, "group_out": 10, "port_out": 2, "group_in": 11, "port_in": 1}
    ]


def test_remove_and_rename():
    cache = PatchbayCache()
    _populate(cache)
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_CONNECTION_REMOVED, 77, 0, 0, 0, 0.0, "")
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_PORT_REMOVED, 10, 2, 0, 0, 0.0, "")
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_CLIENT_RENAMED, 11, 0, 0, 0, 0.0, "Hall")
    cache.on_event(ENGINE_CALLBACK_PATCHBAY_CLIENT_REMOVED, 10, 0, 0, 0, 0.0, "")
    snap = cache.snapshot()
    assert snap["connections"] == []
    assert [g["name"] for g in snap["groups"]] == ["Hall"]


def test_clear_empties_everything():
    cache = PatchbayCache()
    _populate(cache)
    cache.clear()
    assert cache.snapshot() == {"groups": [], "connections": []}


def test_unknown_action_is_ignored():
    cache = PatchbayCache()
    cache.on_event(-1, 0, 0, 0, 0, 0.0, "")
    assert cache.snapshot() == {"groups": [], "connections": []}


def test_events_dispatch_to_registered_cache():
    cache = PatchbayCache()
    events.register(cache)
    try:
        events.dispatch(ENGINE_CALLBACK_PATCHBAY_CLIENT_ADDED, 5, 0, 1, 0, 0.0, "X")
        assert cache.snapshot()["groups"][0]["name"] == "X"
    finally:
        events.register(None)
    events.dispatch(ENGINE_CALLBACK_PATCHBAY_CLIENT_ADDED, 6, 0, 1, 0, 0.0, "Y")  # no-op once unregistered
    assert len(cache.snapshot()["groups"]) == 1
