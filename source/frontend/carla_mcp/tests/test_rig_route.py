"""Tests for RigController.route, unroute, and port-resolution helpers.

Also covers the retrofit of create_track to physically wire via route().
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from carla_mcp.orchestration.jack_router import RouteResult
from carla_mcp.rig.controller import RigController
from carla_mcp.rig.graph import Node, RigGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance(name: str, mcp_port: int = 3003) -> SimpleNamespace:
    """Return a fake CarlaInstance with the attributes the controller reads."""
    return SimpleNamespace(
        name=name,
        jack_client_name=f"CarlaChain_{name}",
        mcp_port=mcp_port,
        is_running=True,
    )


def _make_router(connect_success: bool = True, disconnect_success: bool = True):
    """Return a MagicMock jack_router with configurable default results."""
    router = MagicMock()
    router.connect.return_value = RouteResult(success=connect_success)
    router.disconnect.return_value = RouteResult(success=disconnect_success)
    router.disconnect_client_from_system.return_value = 0
    return router


def _make_controller(
    graph=None,
    list_outputs=None,
    list_inputs=None,
    monitor_ports=None,
    connect_success=True,
):
    """Return (controller, graph, jack_router) with injected port fakes."""
    if graph is None:
        graph = RigGraph()
    instance_manager = MagicMock()
    chain_launcher = MagicMock()
    jack_router = _make_router(connect_success=connect_success)

    ctrl = RigController(
        graph=graph,
        instance_manager=instance_manager,
        chain_launcher=chain_launcher,
        jack_router=jack_router,
        sleep=lambda *_: None,
        list_outputs=list_outputs or (lambda: []),
        list_inputs=list_inputs or (lambda: []),
        monitor_ports=monitor_ports or (lambda: []),
    )
    return ctrl, graph, jack_router, chain_launcher


# ---------------------------------------------------------------------------
# _resolve_stereo_ports
# ---------------------------------------------------------------------------


class TestResolveStereoPorts:
    def _ctrl(self):
        ctrl, _, _, _ = _make_controller()
        return ctrl

    def test_lr_suffix_returns_l_and_r(self):
        ctrl = self._ctrl()
        available = ["foo:bar_l", "foo:bar_r", "other:port"]
        assert ctrl._resolve_stereo_ports("foo:bar", available) == [
            "foo:bar_l",
            "foo:bar_r",
        ]

    def test_12_suffix_returns_1_and_2(self):
        ctrl = self._ctrl()
        available = ["foo:bar1", "foo:bar2"]
        assert ctrl._resolve_stereo_ports("foo:bar", available) == [
            "foo:bar1",
            "foo:bar2",
        ]

    def test_mono_fallback_returns_single_port(self):
        ctrl = self._ctrl()
        available = ["foo:bar", "other:port"]
        assert ctrl._resolve_stereo_ports("foo:bar", available) == ["foo:bar"]

    def test_no_match_returns_empty(self):
        ctrl = self._ctrl()
        available = ["other:port1", "another:thing"]
        assert ctrl._resolve_stereo_ports("foo:bar", available) == []

    def test_lr_takes_priority_over_12(self):
        """When both _l/_r AND 1/2 variants exist, _l/_r wins."""
        ctrl = self._ctrl()
        available = ["foo:bar_l", "foo:bar_r", "foo:bar1", "foo:bar2"]
        result = ctrl._resolve_stereo_ports("foo:bar", available)
        assert result == ["foo:bar_l", "foo:bar_r"]

    def test_only_one_of_lr_does_not_match(self):
        """_l present but _r absent → fall through to 1/2 check."""
        ctrl = self._ctrl()
        available = ["foo:bar_l", "foo:bar1", "foo:bar2"]
        result = ctrl._resolve_stereo_ports("foo:bar", available)
        assert result == ["foo:bar1", "foo:bar2"]


# ---------------------------------------------------------------------------
# _source_ports and _sink_ports
# ---------------------------------------------------------------------------


class TestSourceAndSinkPorts:
    def test_track_source_ports_are_fixed(self):
        ctrl, graph, _, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        node = graph.get_node("a")
        assert ctrl._source_ports(node) == [
            "CarlaChain_a:audio-out1",
            "CarlaChain_a:audio-out2",
        ]

    def test_bus_source_ports_are_fixed(self):
        ctrl, graph, _, _ = _make_controller()
        graph.add_node(Node(name="b", kind="bus", jack_client="CarlaChain_b"))
        node = graph.get_node("b")
        assert ctrl._source_ports(node) == [
            "CarlaChain_b:audio-out1",
            "CarlaChain_b:audio-out2",
        ]

    def test_endpoint_source_ports_use_list_outputs(self):
        outputs = ["looperdooper:loop0_out_l", "looperdooper:loop0_out_r"]
        ctrl, graph, _, _ = _make_controller(list_outputs=lambda: outputs)
        graph.add_node(
            Node(name="loop0", kind="endpoint", jack_client="looperdooper:loop0_out")
        )
        node = graph.get_node("loop0")
        assert ctrl._source_ports(node) == [
            "looperdooper:loop0_out_l",
            "looperdooper:loop0_out_r",
        ]

    def test_track_sink_ports_are_fixed(self):
        ctrl, graph, _, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        node = graph.get_node("a")
        assert ctrl._sink_ports(node) == [
            "CarlaChain_a:audio-in1",
            "CarlaChain_a:audio-in2",
        ]

    def test_out_main_sink_uses_monitor_ports(self):
        monitors = ["alsa_output.usb:playback_AUX0", "alsa_output.usb:playback_AUX1"]
        ctrl, graph, _, _ = _make_controller(monitor_ports=lambda: monitors)
        graph.add_node(
            Node(name="out:main", kind="endpoint", jack_client="out:main")
        )
        node = graph.get_node("out:main")
        assert ctrl._sink_ports(node) == monitors

    def test_other_endpoint_sink_uses_list_inputs(self):
        inputs = ["foo:in_l", "foo:in_r"]
        ctrl, graph, _, _ = _make_controller(list_inputs=lambda: inputs)
        graph.add_node(Node(name="foo", kind="endpoint", jack_client="foo:in"))
        node = graph.get_node("foo")
        assert ctrl._sink_ports(node) == ["foo:in_l", "foo:in_r"]


# ---------------------------------------------------------------------------
# route — track→track
# ---------------------------------------------------------------------------


class TestRouteTrackToTrack:
    def test_connects_stereo_pairs(self):
        ctrl, graph, router, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))

        result = ctrl.route("a", "b")

        assert result["success"] is True
        assert router.connect.call_count == 2
        router.connect.assert_any_call("CarlaChain_a:audio-out1", "CarlaChain_b:audio-in1")
        router.connect.assert_any_call("CarlaChain_a:audio-out2", "CarlaChain_b:audio-in2")

    def test_graph_edge_added(self):
        ctrl, graph, router, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))

        ctrl.route("a", "b")

        edges = graph.edges_from("a")
        assert any(e.dst == "b" for e in edges)

    def test_pairs_in_result(self):
        ctrl, graph, router, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))

        result = ctrl.route("a", "b")

        assert len(result["pairs"]) == 2
        assert ("CarlaChain_a:audio-out1", "CarlaChain_b:audio-in1") in result["pairs"]
        assert ("CarlaChain_a:audio-out2", "CarlaChain_b:audio-in2") in result["pairs"]


# ---------------------------------------------------------------------------
# route — track→out:main (monitor ports)
# ---------------------------------------------------------------------------


class TestRouteTrackToOutMain:
    def test_connects_to_monitor_ports(self):
        monitors = [
            "alsa_output.usb:playback_AUX0",
            "alsa_output.usb:playback_AUX1",
        ]
        ctrl, graph, router, _ = _make_controller(monitor_ports=lambda: monitors)
        graph.add_node(Node(name="mix", kind="track", jack_client="CarlaChain_mix"))

        result = ctrl.route("mix", "out:main")

        assert result["success"] is True
        # out:main node must have been auto-created
        assert graph.has_node("out:main")
        router.connect.assert_any_call(
            "CarlaChain_mix:audio-out1", "alsa_output.usb:playback_AUX0"
        )
        router.connect.assert_any_call(
            "CarlaChain_mix:audio-out2", "alsa_output.usb:playback_AUX1"
        )

    def test_auto_creates_out_main_endpoint(self):
        monitors = ["alsa_output.usb:playback_AUX0", "alsa_output.usb:playback_AUX1"]
        ctrl, graph, router, _ = _make_controller(monitor_ports=lambda: monitors)
        graph.add_node(Node(name="mix", kind="track", jack_client="CarlaChain_mix"))

        assert not graph.has_node("out:main")
        ctrl.route("mix", "out:main")
        assert graph.has_node("out:main")
        node = graph.get_node("out:main")
        assert node.kind == "endpoint"


# ---------------------------------------------------------------------------
# route — endpoint(looperdooper _l/_r)→track
# ---------------------------------------------------------------------------


class TestRouteEndpointLrToTrack:
    def test_resolves_lr_ports_and_connects_to_track_inputs(self):
        outputs = [
            "looperdooper:loop0_out_l",
            "looperdooper:loop0_out_r",
            "other:port",
        ]
        ctrl, graph, router, _ = _make_controller(list_outputs=lambda: outputs)
        graph.add_node(
            Node(
                name="loop0",
                kind="endpoint",
                jack_client="looperdooper:loop0_out",
            )
        )
        graph.add_node(Node(name="track", kind="track", jack_client="CarlaChain_track"))

        result = ctrl.route("loop0", "track")

        assert result["success"] is True
        router.connect.assert_any_call(
            "looperdooper:loop0_out_l", "CarlaChain_track:audio-in1"
        )
        router.connect.assert_any_call(
            "looperdooper:loop0_out_r", "CarlaChain_track:audio-in2"
        )
        assert router.connect.call_count == 2


# ---------------------------------------------------------------------------
# route — pairing logic (mono fan-out and stereo sum)
# ---------------------------------------------------------------------------


class TestRoutePairingLogic:
    def test_mono_src_stereo_dst_fan_out(self):
        """1 src port, 2 dst ports → fan-out: src[0]→dst[0] and src[0]→dst[1]."""
        outputs = ["mono:out"]
        ctrl, graph, router, _ = _make_controller(list_outputs=lambda: outputs)
        graph.add_node(Node(name="mono_ep", kind="endpoint", jack_client="mono:out"))
        graph.add_node(Node(name="trk", kind="track", jack_client="CarlaChain_trk"))

        result = ctrl.route("mono_ep", "trk")

        assert result["success"] is True
        assert router.connect.call_count == 2
        router.connect.assert_any_call("mono:out", "CarlaChain_trk:audio-in1")
        router.connect.assert_any_call("mono:out", "CarlaChain_trk:audio-in2")

    def test_stereo_src_mono_dst_sum(self):
        """2 src ports, 1 dst port → sum: src[0]→dst[0] and src[1]→dst[0]."""
        inputs = ["mono:in"]
        ctrl, graph, router, _ = _make_controller(list_inputs=lambda: inputs)
        graph.add_node(Node(name="trk", kind="track", jack_client="CarlaChain_trk"))
        graph.add_node(
            Node(name="mono_ep", kind="endpoint", jack_client="mono:in")
        )

        result = ctrl.route("trk", "mono_ep")

        assert result["success"] is True
        assert router.connect.call_count == 2
        router.connect.assert_any_call("CarlaChain_trk:audio-out1", "mono:in")
        router.connect.assert_any_call("CarlaChain_trk:audio-out2", "mono:in")


# ---------------------------------------------------------------------------
# route — auto-creates missing endpoint nodes
# ---------------------------------------------------------------------------


class TestRouteAutoCreatesNodes:
    def test_auto_creates_src_endpoint_if_missing(self):
        outputs = ["new:src"]
        ctrl, graph, router, _ = _make_controller(list_outputs=lambda: outputs)
        graph.add_node(Node(name="trk", kind="track", jack_client="CarlaChain_trk"))

        assert not graph.has_node("new:src")
        result = ctrl.route("new:src", "trk")

        assert graph.has_node("new:src")
        ep = graph.get_node("new:src")
        assert ep.kind == "endpoint"
        assert ep.jack_client == "new:src"

    def test_auto_creates_dst_endpoint_if_missing(self):
        inputs = ["new:dst"]
        ctrl, graph, router, _ = _make_controller(list_inputs=lambda: inputs)
        graph.add_node(Node(name="trk", kind="track", jack_client="CarlaChain_trk"))

        assert not graph.has_node("new:dst")
        result = ctrl.route("trk", "new:dst")

        assert graph.has_node("new:dst")

    def test_route_fails_gracefully_when_ports_unresolvable(self):
        ctrl, graph, router, _ = _make_controller(list_outputs=lambda: [])
        graph.add_node(Node(name="ep", kind="endpoint", jack_client="missing:port"))
        graph.add_node(Node(name="trk", kind="track", jack_client="CarlaChain_trk"))

        result = ctrl.route("ep", "trk")

        assert result["success"] is False
        assert "ep" in result["message"]
        router.connect.assert_not_called()


# ---------------------------------------------------------------------------
# route — connect failure
# ---------------------------------------------------------------------------


class TestRouteConnectFailure:
    def test_failure_reported_in_result(self):
        ctrl, graph, router, _ = _make_controller(connect_success=False)
        router.connect.return_value = RouteResult(success=False, message="port busy")
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))

        result = ctrl.route("a", "b")

        assert result["success"] is False
        assert "port busy" in result["message"]


# ---------------------------------------------------------------------------
# unroute
# ---------------------------------------------------------------------------


class TestUnroute:
    def test_disconnect_calls_issued(self):
        ctrl, graph, router, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))
        graph.add_edge("a", "b")

        result = ctrl.unroute("a", "b")

        assert result["success"] is True
        assert router.disconnect.call_count == 2
        router.disconnect.assert_any_call(
            "CarlaChain_a:audio-out1", "CarlaChain_b:audio-in1"
        )
        router.disconnect.assert_any_call(
            "CarlaChain_a:audio-out2", "CarlaChain_b:audio-in2"
        )

    def test_graph_edge_removed(self):
        ctrl, graph, router, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))
        graph.add_edge("a", "b")

        ctrl.unroute("a", "b")

        assert graph.edges_from("a") == []

    def test_missing_src_node_returns_failure(self):
        ctrl, graph, router, _ = _make_controller()
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))

        result = ctrl.unroute("nonexistent", "b")

        assert result["success"] is False
        assert "nonexistent" in result["message"]
        router.disconnect.assert_not_called()

    def test_missing_dst_node_returns_failure(self):
        ctrl, graph, router, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))

        result = ctrl.unroute("a", "nonexistent")

        assert result["success"] is False
        router.disconnect.assert_not_called()

    def test_missing_graph_edge_still_succeeds(self):
        """Unroute should succeed even if no graph edge was recorded."""
        ctrl, graph, router, _ = _make_controller()
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))
        # Intentionally do NOT add the edge.

        result = ctrl.unroute("a", "b")

        assert result["success"] is True
        assert "note" in result["message"].lower() or result["disconnect_failures"] == 0

    def test_disconnect_failures_counted_but_not_fatal(self):
        ctrl, graph, router, _ = _make_controller()
        router.disconnect.return_value = RouteResult(success=False, message="already gone")
        graph.add_node(Node(name="a", kind="track", jack_client="CarlaChain_a"))
        graph.add_node(Node(name="b", kind="track", jack_client="CarlaChain_b"))
        graph.add_edge("a", "b")

        result = ctrl.unroute("a", "b")

        assert result["success"] is True
        assert result["disconnect_failures"] == 2


# ---------------------------------------------------------------------------
# create_track — route integration
# ---------------------------------------------------------------------------


class TestCreateTrackWiresSource:
    def test_jack_router_connect_called_after_create_track(self):
        """create_track must call route(), which calls jack_router.connect."""
        _known = ["in:guitar"]
        ctrl, graph, router, launcher = _make_controller(
            list_outputs=lambda: list(_known),
            list_inputs=lambda: list(_known),
        )
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        # route() for endpoint→track wiring: in:guitar is mono → fan-out to in1 + in2
        assert router.connect.called
        router.connect.assert_any_call("in:guitar", "CarlaChain_strat:audio-in1")
        router.connect.assert_any_call("in:guitar", "CarlaChain_strat:audio-in2")

    def test_result_contains_wiring_key(self):
        _known = ["in:guitar"]
        ctrl, graph, router, launcher = _make_controller(
            list_outputs=lambda: list(_known),
        )
        launcher.launch.return_value = _make_instance("strat")

        result = ctrl.create_track("strat", "in:guitar")

        assert "wiring" in result

    def test_wiring_success_when_ports_resolve(self):
        _known = ["in:guitar"]
        ctrl, graph, router, launcher = _make_controller(
            list_outputs=lambda: list(_known),
        )
        launcher.launch.return_value = _make_instance("strat")

        result = ctrl.create_track("strat", "in:guitar")

        assert result["wiring"]["success"] is True

    def test_create_track_succeeds_even_when_routing_fails(self):
        """Node creation must succeed even if port resolution fails."""
        # list_outputs returns nothing → endpoint port unresolvable → route fails
        ctrl, graph, router, launcher = _make_controller(list_outputs=lambda: [])
        launcher.launch.return_value = _make_instance("strat")

        result = ctrl.create_track("strat", "in:guitar")

        assert result["success"] is True
        assert graph.has_node("strat")
        assert result["wiring"]["success"] is False
        assert "warning" in result

    def test_edge_recorded_in_graph_when_route_succeeds(self):
        _known = ["in:guitar"]
        ctrl, graph, router, launcher = _make_controller(
            list_outputs=lambda: list(_known),
        )
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        edges = graph.edges_from("in:guitar")
        assert any(e.dst == "strat" for e in edges)
