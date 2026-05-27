"""Tests for rig/handles.py — stamp_handle, resolve_handle, read_handle.

Uses a stateful fake host that simulates Carla's volatile plugin-id
behaviour: removing a plugin at index i shifts all higher-indexed plugins
down by one, invalidating their previous IDs.
"""

import pytest

from carla_mcp.rig.handles import stamp_handle, resolve_handle, read_handle, HANDLE_KEY


# ---------------------------------------------------------------------------
# Stateful fake host
# ---------------------------------------------------------------------------

class FakePlugin:
    """Holds the custom-data dict for one plugin slot."""

    def __init__(self) -> None:
        # custom_data[(type_, key)] = value
        self.custom_data: dict[tuple[str, str], str] = {}


class FakeHost:
    """Minimal stateful fake that mimics the Carla host API used by handles.py.

    Plugins are stored in a list.  remove_plugin(i) removes the slot at
    index i and the remaining plugins shift down — identical to what
    Carla does when a plugin is deleted.
    """

    def __init__(self) -> None:
        self._plugins: list[FakePlugin] = []

    # -- host-management helpers (test-only) --------------------------------

    def add_plugin(self) -> int:
        """Add a blank plugin slot and return its new index."""
        self._plugins.append(FakePlugin())
        return len(self._plugins) - 1

    def remove_plugin(self, index: int) -> None:
        """Delete the plugin at *index*; remaining plugins shift down."""
        del self._plugins[index]

    # -- API consumed by handles.py -----------------------------------------

    def get_current_plugin_count(self) -> int:
        return len(self._plugins)

    def set_custom_data(self, plugin_id: int, type_: str, key: str, value: str) -> bool:
        if plugin_id < 0 or plugin_id >= len(self._plugins):
            return False
        self._plugins[plugin_id].custom_data[(type_, key)] = value
        return True

    def get_custom_data_value(self, plugin_id: int, type_: str, key: str):
        if plugin_id < 0 or plugin_id >= len(self._plugins):
            return None
        return self._plugins[plugin_id].custom_data.get((type_, key))


# ---------------------------------------------------------------------------
# stamp_handle
# ---------------------------------------------------------------------------

class TestStampHandle:
    def test_stamp_returns_true(self):
        host = FakeHost()
        host.add_plugin()
        assert stamp_handle(host, 0, "strat/comp") is True

    def test_stamp_stores_handle(self):
        host = FakeHost()
        host.add_plugin()
        stamp_handle(host, 0, "strat/comp")
        assert host.get_custom_data_value(0, "string", HANDLE_KEY) == "strat/comp"

    def test_stamp_invalid_id_returns_false(self):
        host = FakeHost()
        assert stamp_handle(host, 99, "strat/comp") is False


# ---------------------------------------------------------------------------
# read_handle
# ---------------------------------------------------------------------------

class TestReadHandle:
    def test_read_after_stamp(self):
        host = FakeHost()
        host.add_plugin()
        stamp_handle(host, 0, "strat/comp")
        assert read_handle(host, 0) == "strat/comp"

    def test_read_unstamped_returns_none(self):
        host = FakeHost()
        host.add_plugin()
        assert read_handle(host, 0) is None


# ---------------------------------------------------------------------------
# resolve_handle
# ---------------------------------------------------------------------------

class TestResolveHandle:
    def test_resolve_finds_plugin(self):
        host = FakeHost()
        host.add_plugin()  # id 0
        stamp_handle(host, 0, "strat/comp")
        assert resolve_handle(host, "strat/comp") == 0

    def test_resolve_missing_returns_none(self):
        host = FakeHost()
        host.add_plugin()
        stamp_handle(host, 0, "strat/comp")
        assert resolve_handle(host, "nope") is None

    def test_resolve_empty_host_returns_none(self):
        host = FakeHost()
        assert resolve_handle(host, "strat/comp") is None

    def test_resolve_multiple_plugins(self):
        host = FakeHost()
        host.add_plugin()  # id 0
        host.add_plugin()  # id 1
        stamp_handle(host, 0, "a/x")
        stamp_handle(host, 1, "b/y")
        assert resolve_handle(host, "a/x") == 0
        assert resolve_handle(host, "b/y") == 1


# ---------------------------------------------------------------------------
# KEY TEST: plugin removal shifts IDs
# ---------------------------------------------------------------------------

class TestHandleAfterRemoval:
    def test_resolve_survives_lower_plugin_removal(self):
        """Removing plugin 0 shifts plugin 1 to id 0; resolve must follow."""
        host = FakeHost()
        host.add_plugin()  # id 0
        host.add_plugin()  # id 1
        stamp_handle(host, 0, "a/x")
        stamp_handle(host, 1, "b/y")

        # Simulate Carla removing the first plugin; "b/y" is now at id 0
        host.remove_plugin(0)

        assert resolve_handle(host, "b/y") == 0
        assert resolve_handle(host, "a/x") is None

    def test_resolve_after_multiple_removals(self):
        """Three plugins; remove middle one — the last plugin shifts."""
        host = FakeHost()
        host.add_plugin()  # id 0
        host.add_plugin()  # id 1
        host.add_plugin()  # id 2
        stamp_handle(host, 0, "a/x")
        stamp_handle(host, 1, "b/y")
        stamp_handle(host, 2, "c/z")

        host.remove_plugin(1)  # "b/y" is gone; "c/z" is now id 1

        assert resolve_handle(host, "a/x") == 0
        assert resolve_handle(host, "b/y") is None
        assert resolve_handle(host, "c/z") == 1

    def test_read_handle_after_shift(self):
        """read_handle on the shifted id returns the correct handle."""
        host = FakeHost()
        host.add_plugin()  # id 0
        host.add_plugin()  # id 1
        stamp_handle(host, 0, "a/x")
        stamp_handle(host, 1, "b/y")

        host.remove_plugin(0)

        assert read_handle(host, 0) == "b/y"
