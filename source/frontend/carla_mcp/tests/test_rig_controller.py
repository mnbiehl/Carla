"""Tests for rig/controller.py — RigController node lifecycle."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from carla_mcp.rig.graph import RigGraph
from carla_mcp.rig.controller import RigController


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_instance(name: str, mcp_port: int = 3003) -> SimpleNamespace:
    """Return a fake CarlaInstance with the attributes the controller reads."""
    return SimpleNamespace(
        name=name,
        jack_client_name=f"CarlaChain_{name}",
        mcp_port=mcp_port,
        is_running=True,
    )


def _make_controller(graph=None):
    """Return a (controller, graph, mocks) tuple with a no-op sleep.

    Port-listing callables are injected so that route() calls inside
    create_track do not shell out to pw-link.  The lists are populated with
    enough entries so that endpoint port resolution succeeds (mono fallback):
    any port name that matches a node's jack_client verbatim is present.
    The jack_router.connect mock returns a success result by default.
    """
    if graph is None:
        graph = RigGraph()
    instance_manager = MagicMock()
    chain_launcher = MagicMock()
    jack_router = MagicMock()
    jack_router.disconnect_client_from_system.return_value = 0
    # route() calls jack_router.connect; default to success.
    from carla_mcp.orchestration.jack_router import RouteResult
    jack_router.connect.return_value = RouteResult(success=True)
    jack_router.disconnect.return_value = RouteResult(success=True)

    # Provide port lists that satisfy mono-fallback resolution for any
    # endpoint whose jack_client is used directly as a port name (e.g. "in:guitar").
    # Track/bus ports are fixed strings and do not consult these lists.
    _known_endpoints = ["in:guitar", "in:bass", "in:keys", "looperdooper:out"]
    ctrl = RigController(
        graph=graph,
        instance_manager=instance_manager,
        chain_launcher=chain_launcher,
        jack_router=jack_router,
        sleep=lambda *_: None,
        list_outputs=lambda: list(_known_endpoints),
        list_inputs=lambda: list(_known_endpoints),
        monitor_ports=lambda: [],
    )
    return ctrl, graph, chain_launcher, jack_router, instance_manager


# ---------------------------------------------------------------------------
# create_bus
# ---------------------------------------------------------------------------

class TestCreateBus:
    def test_launch_called_with_name(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("reverb")

        result = ctrl.create_bus("reverb")

        launcher.launch.assert_called_once_with("reverb")
        assert result["success"] is True

    def test_settle_calls_disconnect_with_jack_client_name(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        # Return 2 on the first call, then 0 to trigger early-break.
        router.disconnect_client_from_system.side_effect = [2, 0]
        launcher.launch.return_value = _make_instance("reverb")

        ctrl.create_bus("reverb")

        calls = router.disconnect_client_from_system.call_args_list
        assert all(c == call("CarlaChain_reverb") for c in calls)
        assert len(calls) == 2  # removed some, then got 0 → broke early

    def test_graph_gains_bus_node(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("reverb")

        ctrl.create_bus("reverb")

        assert graph.has_node("reverb")
        node = graph.get_node("reverb")
        assert node.kind == "bus"
        assert node.instance == "reverb"
        assert node.jack_client == "CarlaChain_reverb"

    def test_duplicate_name_returns_failure_without_launch(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("reverb")
        ctrl.create_bus("reverb")
        launcher.reset_mock()

        result = ctrl.create_bus("reverb")

        assert result["success"] is False
        launcher.launch.assert_not_called()

    def test_launch_value_error_returns_failure_graph_unchanged(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.side_effect = ValueError("Invalid chain name")

        result = ctrl.create_bus("bad name!")

        assert result["success"] is False
        assert "Invalid chain name" in result["message"]
        assert not graph.has_node("bad name!")

    def test_result_contains_name_and_jack_client(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("main_bus")

        result = ctrl.create_bus("main_bus")

        assert result["name"] == "main_bus"
        assert result["jack_client"] == "CarlaChain_main_bus"


# ---------------------------------------------------------------------------
# create_track
# ---------------------------------------------------------------------------

class TestCreateTrack:
    def test_launch_called_with_track_name(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        launcher.launch.assert_called_once_with("strat")

    def test_auto_creates_endpoint_node_for_source(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        assert graph.has_node("in:guitar")
        ep = graph.get_node("in:guitar")
        assert ep.kind == "endpoint"
        assert ep.jack_client == "in:guitar"

    def test_track_node_has_correct_fields(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        node = graph.get_node("strat")
        assert node.kind == "track"
        assert node.instance == "strat"
        assert node.jack_client == "CarlaChain_strat"
        assert node.source == "in:guitar"

    def test_edge_added_source_to_track(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        edges = graph.edges_from("in:guitar")
        assert len(edges) == 1
        assert edges[0].dst == "strat"

    def test_calls_jack_router_connect_to_wire_source(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")

        result = ctrl.create_track("strat", "in:guitar")

        # create_track now wires the source → track via route(), which calls
        # jack_router.connect for the CarlaChain port pairs.
        assert router.connect.called
        # The result must include wiring info.
        assert "wiring" in result

    def test_source_already_exists_not_duplicated(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        # Pre-add the source endpoint
        from carla_mcp.rig.graph import Node
        graph.add_node(Node(name="in:guitar", kind="endpoint", jack_client="in:guitar"))
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        # Still only one "in:guitar" node
        assert graph.has_node("in:guitar")
        assert len([n for n in graph.nodes if n == "in:guitar"]) == 1

    def test_source_already_exists_edge_still_added(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        from carla_mcp.rig.graph import Node
        graph.add_node(Node(name="in:guitar", kind="endpoint", jack_client="in:guitar"))
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        edges = graph.edges_from("in:guitar")
        assert any(e.dst == "strat" for e in edges)

    def test_duplicate_track_name_returns_failure_no_launch(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")
        ctrl.create_track("strat", "in:guitar")
        launcher.reset_mock()

        result = ctrl.create_track("strat", "in:other")

        assert result["success"] is False
        launcher.launch.assert_not_called()

    def test_launch_failure_does_not_leave_endpoint_node(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.side_effect = ValueError("bad name")

        result = ctrl.create_track("strat!", "in:guitar")

        assert result["success"] is False
        # The endpoint node must NOT have been added (launch failed before that)
        assert not graph.has_node("in:guitar")

    def test_settle_called_with_jack_client_name(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        router.disconnect_client_from_system.side_effect = [1, 0]
        launcher.launch.return_value = _make_instance("strat")

        ctrl.create_track("strat", "in:guitar")

        calls = router.disconnect_client_from_system.call_args_list
        assert all(c == call("CarlaChain_strat") for c in calls)


# ---------------------------------------------------------------------------
# remove_node
# ---------------------------------------------------------------------------

class TestRemoveNode:
    def test_terminate_called_for_track(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")
        ctrl.create_track("strat", "in:guitar")
        launcher.reset_mock()

        result = ctrl.remove_node("strat")

        launcher.terminate.assert_called_once_with("strat")
        assert result["success"] is True

    def test_terminate_called_for_bus(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("fx_bus")
        ctrl.create_bus("fx_bus")
        launcher.reset_mock()

        ctrl.remove_node("fx_bus")

        launcher.terminate.assert_called_once_with("fx_bus")

    def test_node_removed_from_graph(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")
        ctrl.create_track("strat", "in:guitar")

        ctrl.remove_node("strat")

        assert not graph.has_node("strat")

    def test_touching_edges_removed(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")
        ctrl.create_track("strat", "in:guitar")

        ctrl.remove_node("strat")

        assert graph.edges_from("in:guitar") == []

    def test_remove_missing_node_returns_failure(self):
        ctrl, graph, launcher, router, _ = _make_controller()

        result = ctrl.remove_node("nonexistent")

        assert result["success"] is False
        assert "nonexistent" in result["message"]

    def test_endpoint_node_does_not_call_terminate(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        from carla_mcp.rig.graph import Node
        graph.add_node(Node(name="in:guitar", kind="endpoint", jack_client="in:guitar"))

        ctrl.remove_node("in:guitar")

        launcher.terminate.assert_not_called()

    def test_terminate_exception_is_caught_and_node_still_removed(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        launcher.launch.return_value = _make_instance("strat")
        ctrl.create_track("strat", "in:guitar")
        launcher.terminate.side_effect = Exception("process already dead")

        result = ctrl.remove_node("strat")

        # Node should still be removed from graph despite the exception
        assert not graph.has_node("strat")
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Settle loop logic
# ---------------------------------------------------------------------------

class TestSettleLoop:
    def test_settle_runs_up_to_5_iterations_if_always_nonzero(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        # Always returns 1 → never breaks early → runs all 5
        router.disconnect_client_from_system.return_value = 1
        launcher.launch.return_value = _make_instance("x")

        ctrl.create_bus("x")

        assert router.disconnect_client_from_system.call_count == 5

    def test_settle_breaks_early_when_zero_after_some(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        # First pass removes 3, second removes 0 → early break after 2 calls
        router.disconnect_client_from_system.side_effect = [3, 0]
        launcher.launch.return_value = _make_instance("y")

        ctrl.create_bus("y")

        assert router.disconnect_client_from_system.call_count == 2

    def test_settle_does_not_break_early_when_first_pass_is_zero(self):
        ctrl, graph, launcher, router, _ = _make_controller()
        # First pass is 0 — hasn't removed anything yet → no early break
        router.disconnect_client_from_system.return_value = 0
        launcher.launch.return_value = _make_instance("z")

        ctrl.create_bus("z")

        assert router.disconnect_client_from_system.call_count == 5
