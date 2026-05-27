"""Tests for RigController.add_effect and remove_effect (increment 5).

Uses a fake async RemoteInstance injected via remote_factory to record calls
without touching any real Carla process or network.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from carla_mcp.rig.controller import RigController
from carla_mcp.rig.graph import Effect, Node, RigGraph


# ---------------------------------------------------------------------------
# Fake remote
# ---------------------------------------------------------------------------


class FakeRemote:
    """Records async method calls; list_handles returns a configurable mapping."""

    def __init__(self, handles: dict[int, str] | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        # {plugin_id: handle} returned by list_handles
        self._handles: dict[int, str] = handles or {}

    def set_handles(self, handles: dict[int, str]) -> None:
        self._handles = handles

    async def add_plugin(self, plugin_name: str, plugin_type=None) -> str:
        self.calls.append(("add_plugin", plugin_name))
        return "OK"

    async def remove_plugin(self, plugin_id: int) -> str:
        self.calls.append(("remove_plugin", plugin_id))
        return "OK"

    async def set_handle(self, plugin_id: int, handle: str) -> str:
        self.calls.append(("set_handle", (plugin_id, handle)))
        return "OK"

    async def list_handles(self) -> dict[int, str]:
        self.calls.append(("list_handles", None))
        return dict(self._handles)

    async def rewire_chain(self, plugin_ids: list[int]) -> str:
        self.calls.append(("rewire_chain", list(plugin_ids)))
        return json.dumps({"success": True, "plugin_order": plugin_ids, "connections": len(plugin_ids)})

    def call_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args_for(self, name: str) -> list[object]:
        return [args for n, args in self.calls if n == name]


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_controller_with_track(track_name: str = "strat") -> tuple[RigController, RigGraph, FakeRemote]:
    """Return (controller, graph, fake_remote) with a pre-populated track node."""
    graph = RigGraph()
    graph.add_node(Node(name=track_name, kind="track", instance=f"CarlaChain_{track_name}"))

    fake_remote = FakeRemote()

    ctrl = RigController(
        graph=graph,
        instance_manager=MagicMock(),
        chain_launcher=MagicMock(),
        jack_router=MagicMock(),
        sleep=lambda *_: None,
        remote_factory=lambda node: fake_remote,
    )
    return ctrl, graph, fake_remote


# ---------------------------------------------------------------------------
# add_effect
# ---------------------------------------------------------------------------


class TestAddEffect:
    def test_add_first_effect_calls_add_plugin(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        # list_handles returns the newly-stamped handle after add
        fake.set_handles({0: "strat/comp"})

        asyncio.run(ctrl.add_effect("strat", plugin="mcompressor", role="comp"))

        assert ("add_plugin", "mcompressor") in fake.calls

    def test_add_first_effect_calls_set_handle_with_id_0(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        fake.set_handles({0: "strat/comp"})

        asyncio.run(ctrl.add_effect("strat", plugin="mcompressor", role="comp"))

        assert ("set_handle", (0, "strat/comp")) in fake.calls

    def test_add_first_effect_stores_in_graph(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        fake.set_handles({0: "strat/comp"})

        asyncio.run(ctrl.add_effect("strat", plugin="mcompressor", role="comp"))

        node = graph.get_node("strat")
        assert len(node.effects) == 1
        eff = node.effects[0]
        assert eff.role == "comp"
        assert eff.handle == "strat/comp"
        assert eff.plugin == "mcompressor"

    def test_add_first_effect_calls_rewire_with_id_0(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        fake.set_handles({0: "strat/comp"})

        asyncio.run(ctrl.add_effect("strat", plugin="mcompressor", role="comp"))

        assert ("rewire_chain", [0]) in fake.calls

    def test_add_second_effect_calls_set_handle_with_id_1(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        # After first add: {0: "strat/comp"}; after second: {0: "strat/comp", 1: "strat/amp"}
        # list_handles is called once per add_effect; make it return different values each call
        call_count = [0]
        async def _list_handles_seq():
            fake.calls.append(("list_handles", None))
            if call_count[0] == 0:
                call_count[0] += 1
                return {0: "strat/comp"}
            return {0: "strat/comp", 1: "strat/amp"}

        fake.list_handles = _list_handles_seq  # type: ignore[method-assign]

        asyncio.run(ctrl.add_effect("strat", plugin="mcompressor", role="comp"))
        # Reset call tracking for second add
        fake.calls.clear()
        call_count[0] = 0  # reset so second add also starts returning {0: "strat/comp", 1: "strat/amp"}

        asyncio.run(ctrl.add_effect("strat", plugin="mamp", role="amp"))

        assert ("set_handle", (1, "strat/amp")) in fake.calls

    def test_add_second_effect_calls_rewire_with_both_ids(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        # list_handles: first call → {0: comp}, second call → {0: comp, 1: amp}, …
        call_count = [0]
        async def _list_handles_seq():
            fake.calls.append(("list_handles", None))
            call_count[0] += 1
            if call_count[0] <= 1:
                return {0: "strat/comp"}
            return {0: "strat/comp", 1: "strat/amp"}

        fake.list_handles = _list_handles_seq  # type: ignore[method-assign]

        asyncio.run(ctrl.add_effect("strat", plugin="mcompressor", role="comp"))
        fake.calls.clear()

        asyncio.run(ctrl.add_effect("strat", plugin="mamp", role="amp"))

        assert ("rewire_chain", [0, 1]) in fake.calls

    def test_add_effect_refreshes_ids_from_list_handles(self):
        """list_handles returning a shifted mapping is applied to effect.plugin_id."""
        ctrl, graph, fake = _make_controller_with_track("strat")
        # Simulate the child returning id=5 for "strat/comp" (unusual, but tests the refresh)
        fake.set_handles({5: "strat/comp"})

        asyncio.run(ctrl.add_effect("strat", plugin="mcompressor", role="comp"))

        node = graph.get_node("strat")
        assert node.effects[0].plugin_id == 5

    def test_add_effect_on_endpoint_node_returns_failure(self):
        graph = RigGraph()
        graph.add_node(Node(name="in:guitar", kind="endpoint"))
        fake = FakeRemote()
        ctrl = RigController(
            graph=graph,
            instance_manager=MagicMock(),
            chain_launcher=MagicMock(),
            jack_router=MagicMock(),
            sleep=lambda *_: None,
            remote_factory=lambda node: fake,
        )

        result = asyncio.run(ctrl.add_effect("in:guitar", plugin="comp", role="comp"))

        assert result["success"] is False
        assert fake.calls == []

    def test_add_effect_returns_success_dict(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        fake.set_handles({0: "strat/comp"})

        result = asyncio.run(ctrl.add_effect("strat", plugin="mcompressor", role="comp"))

        assert result["success"] is True
        assert result["node"] == "strat"
        assert result["role"] == "comp"
        assert result["handle"] == "strat/comp"

    def test_add_effect_on_missing_node_returns_failure(self):
        graph = RigGraph()
        fake = FakeRemote()
        ctrl = RigController(
            graph=graph,
            instance_manager=MagicMock(),
            chain_launcher=MagicMock(),
            jack_router=MagicMock(),
            sleep=lambda *_: None,
            remote_factory=lambda node: fake,
        )

        result = asyncio.run(ctrl.add_effect("nonexistent", plugin="comp", role="comp"))

        assert result["success"] is False


# ---------------------------------------------------------------------------
# remove_effect
# ---------------------------------------------------------------------------


class TestRemoveEffect:
    def test_remove_effect_calls_remove_plugin_with_resolved_id(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        # Pre-add an effect manually so remove has something to remove
        graph.get_node("strat").effects.append(
            Effect(handle="strat/comp", role="comp", plugin="mcompressor", plugin_id=0)
        )
        # list_handles returns id for that handle; also return empty after removal
        call_count = [0]
        async def _list_handles_seq():
            fake.calls.append(("list_handles", None))
            if call_count[0] == 0:
                call_count[0] += 1
                return {0: "strat/comp"}
            return {}

        fake.list_handles = _list_handles_seq  # type: ignore[method-assign]

        asyncio.run(ctrl.remove_effect("strat", "comp"))

        assert ("remove_plugin", 0) in fake.calls

    def test_remove_effect_removes_from_graph(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        graph.get_node("strat").effects.append(
            Effect(handle="strat/comp", role="comp", plugin="mcompressor", plugin_id=0)
        )
        call_count = [0]
        async def _list_handles_seq():
            fake.calls.append(("list_handles", None))
            if call_count[0] == 0:
                call_count[0] += 1
                return {0: "strat/comp"}
            return {}

        fake.list_handles = _list_handles_seq  # type: ignore[method-assign]

        asyncio.run(ctrl.remove_effect("strat", "comp"))

        node = graph.get_node("strat")
        assert len(node.effects) == 0

    def test_remove_effect_calls_rewire_with_remaining_order(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        # Two effects: comp and amp; remove comp, amp should remain
        graph.get_node("strat").effects.extend([
            Effect(handle="strat/comp", role="comp", plugin="mcompressor", plugin_id=0),
            Effect(handle="strat/amp", role="amp", plugin="mamp", plugin_id=1),
        ])
        call_count = [0]
        async def _list_handles_seq():
            fake.calls.append(("list_handles", None))
            if call_count[0] == 0:
                call_count[0] += 1
                return {0: "strat/comp", 1: "strat/amp"}
            # After removal, amp is now id 0
            return {0: "strat/amp"}

        fake.list_handles = _list_handles_seq  # type: ignore[method-assign]

        asyncio.run(ctrl.remove_effect("strat", "comp"))

        rewire_calls = fake.args_for("rewire_chain")
        assert len(rewire_calls) == 1
        assert rewire_calls[0] == [0]  # amp's refreshed id

    def test_remove_missing_role_returns_failure_no_remote_call(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        fake.set_handles({})

        result = asyncio.run(ctrl.remove_effect("strat", "nonexistent"))

        assert result["success"] is False
        # remove_plugin must NOT have been called
        assert all(name != "remove_plugin" for name, _ in fake.calls)

    def test_remove_effect_returns_success_dict(self):
        ctrl, graph, fake = _make_controller_with_track("strat")
        graph.get_node("strat").effects.append(
            Effect(handle="strat/comp", role="comp", plugin="mcompressor", plugin_id=0)
        )
        fake.set_handles({0: "strat/comp"})

        result = asyncio.run(ctrl.remove_effect("strat", "comp"))

        assert result["success"] is True
        assert result["node"] == "strat"
        assert result["removed"] == "comp"
