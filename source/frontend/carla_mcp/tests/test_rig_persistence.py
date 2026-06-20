"""Tests for RigController.export_rig_state / import_rig_state.

The process-per-track rig keeps each chain in its own child Carla instance, so
persistence must serialize every child's project + the routing graph, then
respawn and restore them.  These tests use a fake remote (records save_project/
load_project + handle calls) injected via remote_factory — no real Carla.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from carla_mcp.rig.controller import RigController
from carla_mcp.rig.graph import Effect, Node, RigGraph
from carla_mcp.orchestration.jack_router import RouteResult


class FakeRemote:
    """Async remote double recording calls; list_handles is configurable."""

    def __init__(self, handles: dict[int, str] | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self._handles: dict[int, str] = handles or {}

    def set_handles(self, handles: dict[int, str]) -> None:
        self._handles = handles

    async def call(self, tool_name: str, **args) -> str:
        self.calls.append((tool_name, args))
        return "OK"

    async def list_handles(self) -> dict[int, str]:
        self.calls.append(("list_handles", None))
        return dict(self._handles)

    async def rewire_chain(self, plugin_ids: list[int]) -> str:
        self.calls.append(("rewire_chain", list(plugin_ids)))
        return "OK"

    def args_for(self, name: str) -> list[object]:
        return [a for n, a in self.calls if n == name]


def _make_instance(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        jack_client_name=f"CarlaChain_{name}",
        mcp_port=3003,
        is_running=True,
    )


def _make_controller(graph: RigGraph, fake: FakeRemote):
    jack_router = MagicMock()
    jack_router.disconnect_client_from_system.return_value = 0
    jack_router.connect.return_value = RouteResult(success=True)
    jack_router.disconnect.return_value = RouteResult(success=True)
    chain_launcher = MagicMock()
    # Ports that satisfy stereo resolution for the loop source + monitors.
    outs = ["loopers:loop0_out_l", "loopers:loop0_out_r"]
    return RigController(
        graph=graph,
        instance_manager=MagicMock(),
        chain_launcher=chain_launcher,
        jack_router=jack_router,
        sleep=lambda *_: None,
        remote_factory=lambda node: fake,
        list_outputs=lambda: list(outs),
        list_inputs=lambda: list(outs),
        monitor_ports=lambda: ["mon_l", "mon_r"],
    ), chain_launcher


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


class TestExportRigState:
    def _graph_with_track(self) -> RigGraph:
        graph = RigGraph()
        graph.add_node(Node(name="loopers:loop0_out", kind="endpoint",
                            jack_client="loopers:loop0_out"))
        graph.add_node(Node(
            name="rhythm", kind="track", instance="CarlaChain_rhythm",
            jack_client="CarlaChain_rhythm", source="loopers:loop0_out",
            effects=[
                Effect(handle="rhythm/eq", role="eq", plugin="x42-eq", plugin_id=0),
                Effect(handle="rhythm/comp", role="comp", plugin="x42-comp", plugin_id=1),
            ],
        ))
        graph.add_edge("loopers:loop0_out", "rhythm")
        return graph

    def test_export_saves_each_child_project(self, tmp_path):
        graph = self._graph_with_track()
        fake = FakeRemote()
        ctrl, _ = _make_controller(graph, fake)

        state = asyncio.run(ctrl.export_rig_state(str(tmp_path / "chains")))

        # The track child was told to save its project to <chains>/rhythm.carxp.
        saved = fake.args_for("save_project")
        assert {"filename": str(tmp_path / "chains" / "rhythm.carxp")} in saved

    def test_export_serializes_nodes_effects_and_edges(self, tmp_path):
        graph = self._graph_with_track()
        fake = FakeRemote()
        ctrl, _ = _make_controller(graph, fake)

        state = asyncio.run(ctrl.export_rig_state(str(tmp_path / "chains")))

        rhythm = next(n for n in state["nodes"] if n["name"] == "rhythm")
        assert rhythm["kind"] == "track"
        assert rhythm["source"] == "loopers:loop0_out"
        assert rhythm["chain_file"].endswith("rhythm.carxp")
        assert [e["role"] for e in rhythm["effects"]] == ["eq", "comp"]
        assert {"src": "loopers:loop0_out", "dst": "rhythm", "gain_db": 0.0} in state["edges"]

    def test_export_endpoint_has_no_chain_file(self, tmp_path):
        graph = self._graph_with_track()
        ctrl, _ = _make_controller(graph, FakeRemote())
        state = asyncio.run(ctrl.export_rig_state(str(tmp_path / "chains")))
        ep = next(n for n in state["nodes"] if n["name"] == "loopers:loop0_out")
        assert "chain_file" not in ep


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


class TestImportRigState:
    def _state(self, chain_file: str) -> dict:
        return {
            "version": 1,
            "nodes": [
                {"name": "loopers:loop0_out", "kind": "endpoint",
                 "jack_client": "loopers:loop0_out", "source": None, "effects": []},
                {"name": "rhythm", "kind": "track", "instance": "CarlaChain_rhythm",
                 "jack_client": "CarlaChain_rhythm", "source": "loopers:loop0_out",
                 "chain_file": chain_file,
                 "effects": [
                     {"role": "eq", "handle": "rhythm/eq", "plugin": "x42-eq", "bypassed": False},
                     {"role": "comp", "handle": "rhythm/comp", "plugin": "x42-comp", "bypassed": False},
                 ]},
            ],
            "edges": [
                {"src": "loopers:loop0_out", "dst": "rhythm", "gain_db": 0.0},
                {"src": "rhythm", "dst": "out:main", "gain_db": 0.0},
            ],
        }

    def test_import_respawns_track_and_restores_chain(self, tmp_path):
        chain_file = tmp_path / "chains" / "rhythm.carxp"
        chain_file.parent.mkdir(parents=True)
        chain_file.write_text("<CARLA-PROJECT/>")

        graph = RigGraph()
        fake = FakeRemote({0: "rhythm/eq", 1: "rhythm/comp"})
        ctrl, launcher = _make_controller(graph, fake)
        launcher.launch.return_value = _make_instance("rhythm")

        result = asyncio.run(ctrl.import_rig_state(self._state(str(chain_file)),
                                                   str(tmp_path / "chains")))

        assert result["success"] is True
        # Child respawned and its saved project reloaded.
        launcher.launch.assert_called_once_with("rhythm")
        assert {"filename": str(chain_file)} in fake.args_for("load_project")
        # Graph chain rebuilt with resolved plugin ids, then rewired in order.
        node = graph.get_node("rhythm")
        assert [e.role for e in node.effects] == ["eq", "comp"]
        assert [e.plugin_id for e in node.effects] == [0, 1]
        assert ("rewire_chain", [0, 1]) in fake.calls

    def test_import_reapplies_extra_routing_edges(self, tmp_path):
        chain_file = tmp_path / "chains" / "rhythm.carxp"
        chain_file.parent.mkdir(parents=True)
        chain_file.write_text("<CARLA-PROJECT/>")

        graph = RigGraph()
        fake = FakeRemote({0: "rhythm/eq", 1: "rhythm/comp"})
        ctrl, launcher = _make_controller(graph, fake)
        launcher.launch.return_value = _make_instance("rhythm")

        asyncio.run(ctrl.import_rig_state(self._state(str(chain_file)),
                                          str(tmp_path / "chains")))

        # rhythm -> out:main edge was applied (out:main auto-created as endpoint).
        assert graph.has_node("out:main")
        assert any(e.src == "rhythm" and e.dst == "out:main" for e in graph.edges)

    def test_import_reports_unresolved_handles(self, tmp_path):
        chain_file = tmp_path / "chains" / "rhythm.carxp"
        chain_file.parent.mkdir(parents=True)
        chain_file.write_text("<CARLA-PROJECT/>")

        graph = RigGraph()
        # Only one of the two handles resolves after restore.
        fake = FakeRemote({0: "rhythm/eq"})
        ctrl, launcher = _make_controller(graph, fake)
        launcher.launch.return_value = _make_instance("rhythm")

        result = asyncio.run(ctrl.import_rig_state(self._state(str(chain_file)),
                                                   str(tmp_path / "chains")))

        assert any("did not resolve" in m for m in result["messages"])
