"""End-to-end controller-level test for the rig layer.

Builds a RigController with all dependencies mocked, runs the full
worked-example script from the spec, and asserts that describe_rig output
contains the expected chains and routing lines.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from carla_mcp.rig.controller import RigController
from carla_mcp.rig.describe import describe_rig
from carla_mcp.rig.graph import RigGraph
from carla_mcp.orchestration.jack_router import RouteResult


# ---------------------------------------------------------------------------
# Fake RemoteInstance
# ---------------------------------------------------------------------------


class FakeRemote:
    """Per-node fake RemoteInstance with realistic handle/ID tracking.

    Each add_plugin call appends a new (id → handle) entry.
    set_handle records the handle for that id.
    list_handles returns the current {id: handle} dict.
    rewire_chain / remove_plugin are recorded as no-ops.
    """

    def __init__(self) -> None:
        self._plugins: list[str] = []          # plugin name by id
        self._handles: dict[int, str] = {}     # id → handle
        self.calls: list[tuple] = []

    async def add_plugin(self, plugin_name: str, plugin_type=None) -> str:
        new_id = len(self._plugins)
        self._plugins.append(plugin_name)
        self.calls.append(("add_plugin", plugin_name))
        return "OK"

    async def set_handle(self, plugin_id: int, handle: str) -> str:
        self._handles[plugin_id] = handle
        self.calls.append(("set_handle", (plugin_id, handle)))
        return "OK"

    async def list_handles(self) -> dict[int, str]:
        self.calls.append(("list_handles", None))
        return dict(self._handles)

    async def rewire_chain(self, plugin_ids: list[int]) -> str:
        self.calls.append(("rewire_chain", list(plugin_ids)))
        return json.dumps({"success": True, "plugin_order": plugin_ids, "connections": 0})

    async def remove_plugin(self, plugin_id: int) -> str:
        self.calls.append(("remove_plugin", plugin_id))
        return "OK"

    async def set_active(self, plugin_id: int, active: bool) -> str:
        self.calls.append(("set_active", (plugin_id, active)))
        return "OK"

    async def get_parameters(self, plugin_id: int) -> list[dict]:
        self.calls.append(("get_parameters", plugin_id))
        return []


# ---------------------------------------------------------------------------
# Controller factory
# ---------------------------------------------------------------------------


def _make_controller() -> tuple[RigController, RigGraph, dict[str, FakeRemote]]:
    """Return a controller wired with all mocked dependencies.

    remote_factory returns a per-node FakeRemote (keyed by node.name).
    jack_router.connect and .disconnect always return success.
    Capture ports include "in:guitar" and "in:mic" so mono-fallback resolution
    in _resolve_stereo_ports succeeds.
    """
    graph = RigGraph()

    # Per-node remotes — created lazily on first access
    remotes: dict[str, FakeRemote] = {}

    def remote_factory(node):
        if node.name not in remotes:
            remotes[node.name] = FakeRemote()
        return remotes[node.name]

    jack_router = MagicMock()
    jack_router.disconnect_client_from_system.return_value = 0
    jack_router.connect.return_value = RouteResult(success=True)
    jack_router.disconnect.return_value = RouteResult(success=True)

    instance_manager = MagicMock()
    chain_launcher = MagicMock()

    # capture ports that satisfy mono-fallback resolution
    capture_ports = ["in:guitar", "in:mic"]
    # monitor port so that route to "out:main" can resolve its sink
    monitor_output_ports = ["alsa_output.pro-output:playback_AUX0"]

    ctrl = RigController(
        graph=graph,
        instance_manager=instance_manager,
        chain_launcher=chain_launcher,
        jack_router=jack_router,
        sleep=lambda *_: None,
        remote_factory=remote_factory,
        list_outputs=lambda: list(capture_ports),
        list_inputs=lambda: list(capture_ports),
        monitor_ports=lambda: list(monitor_output_ports),
    )
    return ctrl, graph, remotes


def _fake_instance(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        jack_client_name=f"CarlaChain_{name}",
        mcp_port=3100,
        is_running=True,
    )


# ---------------------------------------------------------------------------
# The worked example
# ---------------------------------------------------------------------------


class TestRigE2EWorkedExample:
    """Run the full spec worked example and assert describe_rig output."""

    def test_full_script(self):
        ctrl, graph, remotes = _make_controller()

        # Wire chain_launcher.launch to return fake instances
        ctrl._chain_launcher.launch.side_effect = _fake_instance

        # --- create_track ---
        r = ctrl.create_track("strat", "in:guitar")
        assert r["success"] is True, f"create_track strat failed: {r}"

        r = ctrl.create_track("vocals", "in:mic")
        assert r["success"] is True, f"create_track vocals failed: {r}"

        # --- create_bus ---
        r = ctrl.create_bus("reverb")
        assert r["success"] is True, f"create_bus reverb failed: {r}"

        # --- add_effect calls (async) ---
        asyncio.run(ctrl.add_effect("strat", "LSP Compressor", "comp"))
        asyncio.run(ctrl.add_effect("strat", "GxAmplifier", "amp"))

        asyncio.run(ctrl.add_effect("vocals", "LSP Gate", "gate"))
        asyncio.run(ctrl.add_effect("vocals", "LSP Compressor", "comp"))

        asyncio.run(ctrl.add_effect("reverb", "Dragonfly Hall", "verb"))

        # --- route ---
        r = ctrl.route("strat", "out:main")
        assert r["success"] is True, f"route strat→out:main failed: {r}"
        r = ctrl.route("strat", "reverb")
        assert r["success"] is True, f"route strat→reverb failed: {r}"
        r = ctrl.route("vocals", "out:main")
        assert r["success"] is True, f"route vocals→out:main failed: {r}"
        r = ctrl.route("vocals", "reverb")
        assert r["success"] is True, f"route vocals→reverb failed: {r}"
        r = ctrl.route("reverb", "out:main")
        assert r["success"] is True, f"route reverb→out:main failed: {r}"

        # --- assert describe_rig output ---
        description = describe_rig(graph)

        # Chain lines
        assert "strat" in description
        assert "comp" in description
        assert "amp" in description
        assert "gate" in description
        assert "verb" in description
        # Chains section: comp ▸ amp for strat and gate ▸ comp for vocals
        assert "comp ▸ amp" in description
        assert "gate ▸ comp" in description
        # Track suffix
        assert "(loop: dry)" in description
        # Bus chain: verb for reverb
        assert "reverb: verb" in description

        # Routing lines
        assert "strat → out:main" in description
        assert "strat → reverb" in description
        assert "vocals → out:main" in description
        assert "vocals → reverb" in description
        assert "reverb → out:main" in description

    def test_remotes_received_correct_plugins(self):
        """Verify each per-node FakeRemote received the right add_plugin calls."""
        ctrl, graph, remotes = _make_controller()
        ctrl._chain_launcher.launch.side_effect = _fake_instance

        ctrl.create_track("strat", "in:guitar")
        ctrl.create_track("vocals", "in:mic")
        ctrl.create_bus("reverb")

        asyncio.run(ctrl.add_effect("strat", "LSP Compressor", "comp"))
        asyncio.run(ctrl.add_effect("strat", "GxAmplifier", "amp"))
        asyncio.run(ctrl.add_effect("vocals", "LSP Gate", "gate"))
        asyncio.run(ctrl.add_effect("vocals", "LSP Compressor", "comp"))
        asyncio.run(ctrl.add_effect("reverb", "Dragonfly Hall", "verb"))

        strat_plugins = [a for n, a in remotes["strat"].calls if n == "add_plugin"]
        assert strat_plugins == ["LSP Compressor", "GxAmplifier"]

        vocals_plugins = [a for n, a in remotes["vocals"].calls if n == "add_plugin"]
        assert vocals_plugins == ["LSP Gate", "LSP Compressor"]

        reverb_plugins = [a for n, a in remotes["reverb"].calls if n == "add_plugin"]
        assert reverb_plugins == ["Dragonfly Hall"]

    def test_effects_chain_order_in_graph(self):
        """Verify effects are ordered correctly in the graph after all adds."""
        ctrl, graph, remotes = _make_controller()
        ctrl._chain_launcher.launch.side_effect = _fake_instance

        ctrl.create_track("strat", "in:guitar")
        asyncio.run(ctrl.add_effect("strat", "LSP Compressor", "comp"))
        asyncio.run(ctrl.add_effect("strat", "GxAmplifier", "amp"))

        strat_node = graph.get_node("strat")
        roles = [e.role for e in strat_node.effects]
        assert roles == ["comp", "amp"]
