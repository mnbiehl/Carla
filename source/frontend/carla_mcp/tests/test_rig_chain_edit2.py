"""Tests for RigController.move_effect, bypass, and set_param (increment 5b).

Uses a fake async RemoteInstance injected via remote_factory to record calls
without touching any real Carla process or network.  Extends the pattern from
test_rig_chain_edit.py.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from carla_mcp.rig.controller import RigController
from carla_mcp.rig.graph import Effect, Node, RigGraph


# ---------------------------------------------------------------------------
# Fake remote
# ---------------------------------------------------------------------------


class FakeRemote:
    """Records async method calls; configurable responses for list_handles and
    get_parameters."""

    def __init__(
        self,
        handles: dict[int, str] | None = None,
        parameters: list[dict] | None = None,
    ) -> None:
        self.calls: list[tuple[str, object]] = []
        self._handles: dict[int, str] = handles or {}
        self._parameters: list[dict] = parameters or []

    def set_handles(self, handles: dict[int, str]) -> None:
        self._handles = handles

    def set_parameters(self, parameters: list[dict]) -> None:
        self._parameters = parameters

    async def add_plugin(self, plugin_name: str, plugin_type=None) -> str:
        self.calls.append(("add_plugin", plugin_name))
        return "OK"

    async def remove_plugin(self, plugin_id: int) -> str:
        self.calls.append(("remove_plugin", plugin_id))
        return "OK"

    async def set_parameter(self, plugin_id: int, parameter_id: int, value: float) -> str:
        self.calls.append(("set_parameter", (plugin_id, parameter_id, value)))
        return "OK"

    async def set_handle(self, plugin_id: int, handle: str) -> str:
        self.calls.append(("set_handle", (plugin_id, handle)))
        return "OK"

    async def list_handles(self) -> dict[int, str]:
        self.calls.append(("list_handles", None))
        return dict(self._handles)

    async def rewire_chain(self, plugin_ids: list[int]) -> str:
        self.calls.append(("rewire_chain", list(plugin_ids)))
        return json.dumps({"success": True, "plugin_order": plugin_ids})

    async def set_active(self, plugin_id: int, active: bool) -> str:
        self.calls.append(("set_active", (plugin_id, active)))
        return "OK"

    async def get_parameters(self, plugin_id: int) -> list[dict]:
        self.calls.append(("get_parameters", plugin_id))
        return list(self._parameters)

    def call_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args_for(self, name: str) -> list[object]:
        return [args for n, args in self.calls if n == name]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_controller_with_track_and_effects(
    track_name: str = "strat",
    effects: list[Effect] | None = None,
    handles: dict[int, str] | None = None,
    parameters: list[dict] | None = None,
) -> tuple[RigController, RigGraph, FakeRemote]:
    """Return (controller, graph, fake_remote) with a pre-populated track."""
    graph = RigGraph()
    node = Node(name=track_name, kind="track", instance=f"CarlaChain_{track_name}")
    graph.add_node(node)

    if effects:
        for eff in effects:
            node.effects.append(eff)

    # Default handles: map each effect's plugin_id to its handle
    if handles is None and effects:
        handles = {eff.plugin_id: eff.handle for eff in effects if eff.plugin_id is not None}

    fake_remote = FakeRemote(handles=handles or {}, parameters=parameters or [])

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
# move_effect
# ---------------------------------------------------------------------------


class TestMoveEffect:
    """Tests for RigController.move_effect."""

    def _three_effect_setup(self) -> tuple[RigController, RigGraph, FakeRemote]:
        effects = [
            Effect(handle="strat/comp", role="comp", plugin="mcompressor", plugin_id=0),
            Effect(handle="strat/eq", role="eq", plugin="mequalizer", plugin_id=1),
            Effect(handle="strat/amp", role="amp", plugin="mamp", plugin_id=2),
        ]
        return _make_controller_with_track_and_effects("strat", effects=effects)

    def test_move_to_end_reorders_graph(self):
        ctrl, graph, fake = self._three_effect_setup()

        result = asyncio.run(ctrl.move_effect("strat", "comp", "end"))

        assert result["success"] is True
        node = graph.get_node("strat")
        assert [e.role for e in node.effects] == ["eq", "amp", "comp"]

    def test_move_to_start_reorders_graph(self):
        ctrl, graph, fake = self._three_effect_setup()

        result = asyncio.run(ctrl.move_effect("strat", "amp", "start"))

        assert result["success"] is True
        node = graph.get_node("strat")
        assert [e.role for e in node.effects] == ["amp", "comp", "eq"]

    def test_move_calls_rewire_chain_with_new_plugin_id_order(self):
        ctrl, graph, fake = self._three_effect_setup()

        asyncio.run(ctrl.move_effect("strat", "comp", "end"))

        rewire_calls = fake.args_for("rewire_chain")
        assert len(rewire_calls) == 1
        # After move: eq(1), amp(2), comp(0)
        assert rewire_calls[0] == [1, 2, 0]

    def test_move_returns_order_in_success_dict(self):
        ctrl, graph, fake = self._three_effect_setup()

        result = asyncio.run(ctrl.move_effect("strat", "comp", "end"))

        assert result["success"] is True
        assert result["order"] == [1, 2, 0]

    def test_bad_role_returns_failure_dict(self):
        ctrl, graph, fake = self._three_effect_setup()
        fake.calls.clear()

        result = asyncio.run(ctrl.move_effect("strat", "nonexistent", "end"))

        assert result["success"] is False
        assert "nonexistent" in result["message"]

    def test_bad_role_does_not_call_rewire(self):
        ctrl, graph, fake = self._three_effect_setup()
        fake.calls.clear()

        asyncio.run(ctrl.move_effect("strat", "nonexistent", "end"))

        assert "rewire_chain" not in fake.call_names()

    def test_move_missing_node_returns_failure(self):
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

        result = asyncio.run(ctrl.move_effect("nonexistent", "comp", "end"))

        assert result["success"] is False

    def test_move_endpoint_node_returns_failure(self):
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

        result = asyncio.run(ctrl.move_effect("in:guitar", "comp", "end"))

        assert result["success"] is False


# ---------------------------------------------------------------------------
# bypass
# ---------------------------------------------------------------------------


class TestBypass:
    """Tests for RigController.bypass."""

    def _setup(self) -> tuple[RigController, RigGraph, FakeRemote]:
        effects = [
            Effect(handle="strat/comp", role="comp", plugin="mcompressor", plugin_id=0),
            Effect(handle="strat/eq", role="eq", plugin="mequalizer", plugin_id=1),
        ]
        return _make_controller_with_track_and_effects("strat", effects=effects)

    def test_bypass_on_calls_set_active_false(self):
        ctrl, graph, fake = self._setup()

        asyncio.run(ctrl.bypass("strat", "comp", on=True))

        assert ("set_active", (0, False)) in fake.calls

    def test_bypass_on_sets_effect_bypassed_true(self):
        ctrl, graph, fake = self._setup()

        asyncio.run(ctrl.bypass("strat", "comp", on=True))

        effect = graph.get_node("strat").effects[0]
        assert effect.bypassed is True

    def test_bypass_off_calls_set_active_true(self):
        ctrl, graph, fake = self._setup()
        # Pre-bypass the effect
        graph.get_node("strat").effects[0].bypassed = True

        asyncio.run(ctrl.bypass("strat", "comp", on=False))

        assert ("set_active", (0, True)) in fake.calls

    def test_bypass_off_sets_effect_bypassed_false(self):
        ctrl, graph, fake = self._setup()
        graph.get_node("strat").effects[0].bypassed = True

        asyncio.run(ctrl.bypass("strat", "comp", on=False))

        effect = graph.get_node("strat").effects[0]
        assert effect.bypassed is False

    def test_bypass_returns_success_dict_with_node_role_bypassed(self):
        ctrl, graph, fake = self._setup()

        result = asyncio.run(ctrl.bypass("strat", "comp", on=True))

        assert result["success"] is True
        assert result["node"] == "strat"
        assert result["role"] == "comp"
        assert result["bypassed"] is True

    def test_bypass_default_on_is_true(self):
        ctrl, graph, fake = self._setup()

        # Call without explicit `on` argument
        result = asyncio.run(ctrl.bypass("strat", "comp"))

        assert result["success"] is True
        assert result["bypassed"] is True
        assert ("set_active", (0, False)) in fake.calls

    def test_bypass_missing_effect_returns_failure(self):
        ctrl, graph, fake = self._setup()
        fake.calls.clear()

        result = asyncio.run(ctrl.bypass("strat", "nonexistent", on=True))

        assert result["success"] is False
        assert "nonexistent" in result["message"]

    def test_bypass_missing_effect_does_not_call_set_active(self):
        ctrl, graph, fake = self._setup()
        fake.calls.clear()

        asyncio.run(ctrl.bypass("strat", "nonexistent", on=True))

        assert "set_active" not in fake.call_names()

    def test_bypass_missing_node_returns_failure(self):
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

        result = asyncio.run(ctrl.bypass("nonexistent", "comp", on=True))

        assert result["success"] is False

    def test_bypass_endpoint_node_returns_failure(self):
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

        result = asyncio.run(ctrl.bypass("in:guitar", "comp", on=True))

        assert result["success"] is False


# ---------------------------------------------------------------------------
# set_param
# ---------------------------------------------------------------------------


class TestSetParam:
    """Tests for RigController.set_param."""

    # Fake parameter list — Threshold at index 0, Ratio at index 1
    _PARAMS = [
        {"name": "Threshold", "index": 0, "min": -60.0, "max": 0.0, "default": -20.0},
        {"name": "Ratio", "index": 1, "min": 1.0, "max": 20.0, "default": 4.0},
    ]

    def _setup(
        self, parameters: list[dict] | None = None
    ) -> tuple[RigController, RigGraph, FakeRemote]:
        effects = [
            Effect(handle="strat/comp", role="comp", plugin="mcompressor", plugin_id=0),
        ]
        return _make_controller_with_track_and_effects(
            "strat", effects=effects, parameters=parameters or self._PARAMS
        )

    def test_set_param_calls_set_parameter_with_resolved_index(self):
        ctrl, graph, fake = self._setup()

        asyncio.run(ctrl.set_param("strat", "comp", "Threshold", -30.0))

        assert ("set_parameter", (0, 0, -30.0)) in fake.calls

    def test_set_param_case_insensitive_name_match(self):
        ctrl, graph, fake = self._setup()

        asyncio.run(ctrl.set_param("strat", "comp", "threshold", -30.0))

        assert ("set_parameter", (0, 0, -30.0)) in fake.calls

    def test_set_param_second_param_by_index(self):
        ctrl, graph, fake = self._setup()

        asyncio.run(ctrl.set_param("strat", "comp", "Ratio", 8.0))

        assert ("set_parameter", (0, 1, 8.0)) in fake.calls

    def test_set_param_returns_success_dict_with_param_index(self):
        ctrl, graph, fake = self._setup()

        result = asyncio.run(ctrl.set_param("strat", "comp", "Threshold", -30.0))

        assert result["success"] is True
        assert result["node"] == "strat"
        assert result["role"] == "comp"
        assert result["param"] == "Threshold"
        assert result["param_index"] == 0
        assert result["value"] == -30.0

    def test_set_param_returns_range_fields_from_param_dict(self):
        ctrl, graph, fake = self._setup()

        result = asyncio.run(ctrl.set_param("strat", "comp", "Threshold", -30.0))

        assert result["min"] == -60.0
        assert result["max"] == 0.0
        assert result["default"] == -20.0

    def test_unknown_param_name_returns_failure(self):
        ctrl, graph, fake = self._setup()
        fake.calls.clear()

        result = asyncio.run(ctrl.set_param("strat", "comp", "NoSuchParam", 0.0))

        assert result["success"] is False
        assert "NoSuchParam" in result["message"]

    def test_unknown_param_name_does_not_call_set_parameter(self):
        ctrl, graph, fake = self._setup()
        fake.calls.clear()

        asyncio.run(ctrl.set_param("strat", "comp", "NoSuchParam", 0.0))

        assert "set_parameter" not in fake.call_names()

    def test_set_param_missing_effect_returns_failure(self):
        ctrl, graph, fake = self._setup()

        result = asyncio.run(ctrl.set_param("strat", "nonexistent", "Threshold", -30.0))

        assert result["success"] is False

    def test_set_param_missing_node_returns_failure(self):
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

        result = asyncio.run(ctrl.set_param("nonexistent", "comp", "Threshold", -30.0))

        assert result["success"] is False

    def test_set_param_fallback_to_list_position_when_no_index_key(self):
        """If the param dict has no 'index'/'id'/'parameter_id', fall back to list position."""
        params_no_index = [
            {"name": "Gain", "min": -20.0, "max": 20.0},
            {"name": "Treble", "min": -10.0, "max": 10.0},
        ]
        ctrl, graph, fake = self._setup(parameters=params_no_index)

        # "Treble" is at list position 1
        asyncio.run(ctrl.set_param("strat", "comp", "Treble", 5.0))

        assert ("set_parameter", (0, 1, 5.0)) in fake.calls

    def test_set_param_handles_id_key_instead_of_index(self):
        """Controller accepts 'id' as the numeric index key."""
        params_with_id = [
            {"name": "Attack", "id": 3, "min": 0.0, "max": 500.0},
        ]
        ctrl, graph, fake = self._setup(parameters=params_with_id)

        asyncio.run(ctrl.set_param("strat", "comp", "Attack", 100.0))

        assert ("set_parameter", (0, 3, 100.0)) in fake.calls

    def test_set_param_endpoint_node_returns_failure(self):
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

        result = asyncio.run(ctrl.set_param("in:guitar", "comp", "Gain", 0.0))

        assert result["success"] is False
