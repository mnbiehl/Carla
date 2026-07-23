"""Tests for observe() assembly and controller.snapshot_handles."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from carla_mcp.rig.controller import RigController
from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, observe


class TestObserve:
    def test_assembles_snapshot_from_callables(self):
        units = [RuntimeUnit(name="carla:main", kind="carla-main"),
                 RuntimeUnit(name="looper:engine", kind="looper-engine")]

        async def get_state():
            return {"loopers": []}

        async def get_handles():
            return {"strat": {"0": "strat/eq"}}

        obs = asyncio.run(observe(
            units,
            list_links=lambda: [("a:1", "b:1")],
            list_outputs=lambda: ["a:1"],
            list_inputs=lambda: ["b:1"],
            unit_probe=lambda u: u.kind == "carla-main",
            looper_get_state=get_state,
            carla_handles=get_handles,
        ))
        assert obs.links == [Link("a:1", "b:1")]
        assert obs.unit_status == {"carla:main": True, "looper:engine": False}
        assert obs.looper_state == {"loopers": []}
        assert obs.instance_handles == {"strat": {"0": "strat/eq"}}

    def test_probe_failures_never_raise(self):
        async def broken():
            raise ConnectionError("down")

        def broken_sync():
            raise OSError("pw gone")

        obs = asyncio.run(observe(
            [RuntimeUnit(name="a2j", kind="a2j")],
            list_links=broken_sync,
            list_outputs=broken_sync,
            list_inputs=broken_sync,
            unit_probe=lambda u: (_ for _ in ()).throw(OSError("boom")),
            looper_get_state=broken,
            carla_handles=broken,
        ))
        assert obs.links == [] and obs.output_ports == []
        assert obs.unit_status == {"a2j": False}
        assert obs.looper_state is None
        assert obs.instance_handles == {}


class TestSnapshotHandles:
    def test_collects_per_node_handles_and_errors(self):
        graph = RigGraph()
        graph.add_node(Node(name="strat", kind="track", instance="strat"))
        graph.add_node(Node(name="bass", kind="track", instance="bass"))
        graph.add_node(Node(name="in:guitar", kind="endpoint"))

        good = MagicMock()
        good.list_handles = AsyncMock(return_value={0: "strat/eq"})
        bad = MagicMock()
        bad.list_handles = AsyncMock(side_effect=RuntimeError("child dead"))

        def factory(node):
            return good if node.name == "strat" else bad

        controller = RigController(
            graph, MagicMock(), MagicMock(), MagicMock(),
            sleep=lambda *_: None, remote_factory=factory,
        )
        result = asyncio.run(controller.snapshot_handles())
        assert result["nodes"] == {"strat": {"0": "strat/eq"}}
        assert result["errors"] == ["bass: child dead"]
