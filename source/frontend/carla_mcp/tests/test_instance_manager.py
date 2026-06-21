"""Tests for multi-instance Carla management."""

import socket

import pytest
from unittest.mock import Mock, patch
from carla_mcp.state.instance_manager import CarlaInstance, InstanceManager


class TestCarlaInstance:
    """Test CarlaInstance data structure."""

    def test_new_instance_has_defaults(self):
        """New instance has expected default values."""
        inst = CarlaInstance(name="guitar")
        assert inst.mcp_port is None
        assert inst.jack_client_name is None
        assert inst.headless is False
        assert not inst.is_running

    def test_instance_creation(self):
        """Can create instance with name."""
        instance = CarlaInstance(name="main")

        assert instance.name == "main"
        assert instance.headless is False
        assert instance.process is None
        assert instance.host is None

    def test_instance_not_running_initially(self):
        """New instance is not running."""
        instance = CarlaInstance(name="test")

        assert not instance.is_running

    def test_is_running_checks_process_poll(self):
        """is_running returns True when process.poll() is None."""
        proc = Mock()
        proc.poll.return_value = None
        inst = CarlaInstance(name="guitar", process=proc)
        assert inst.is_running

    def test_is_running_false_when_process_exited(self):
        """is_running returns False when process has exited."""
        proc = Mock()
        proc.poll.return_value = 0
        inst = CarlaInstance(name="guitar", process=proc)
        assert not inst.is_running


class TestInstanceManagerPortAllocation:
    """Test port allocation and release."""

    @pytest.fixture(autouse=True)
    def _all_ports_free(self):
        """Treat every candidate port as free unless a test overrides it.

        allocate_port() bind-tests each port; these tests assert exact port
        numbers, so stub the probe to stay independent of the test host.
        Individual tests re-patch ``_port_in_use`` to exercise skip behaviour.
        """
        with patch.object(InstanceManager, "_port_in_use", return_value=False):
            yield

    def test_allocates_sequential_ports(self):
        """Ports are allocated sequentially from base."""
        mgr = InstanceManager(base_mcp_port=3003)
        assert mgr.allocate_port() == 3003
        assert mgr.allocate_port() == 3004

    def test_reclaims_released_ports(self):
        """Released ports are reused before allocating new ones."""
        mgr = InstanceManager(base_mcp_port=3003)
        port = mgr.allocate_port()
        mgr.release_port(port)
        assert mgr.allocate_port() == 3003

    def test_release_then_allocate_multiple(self):
        """Multiple released ports are all reusable."""
        mgr = InstanceManager(base_mcp_port=3003)
        p1 = mgr.allocate_port()
        p2 = mgr.allocate_port()
        mgr.release_port(p1)
        mgr.release_port(p2)
        reclaimed = {mgr.allocate_port(), mgr.allocate_port()}
        assert reclaimed == {3003, 3004}

    def test_default_base_port(self):
        """Default base port is 3003 (3002 reserved for looper)."""
        mgr = InstanceManager()
        assert mgr.allocate_port() == 3003

    def test_skips_in_use_ports(self):
        """A candidate port already bound by another service is skipped."""
        mgr = InstanceManager(base_mcp_port=3003)
        with patch.object(mgr, "_port_in_use", side_effect=lambda p: p == 3003):
            # 3003 is taken (e.g. by a stray process), so we get 3004.
            assert mgr.allocate_port() == 3004
            assert mgr.allocate_port() == 3005

    def test_skips_released_port_if_now_taken(self):
        """A released port that has since been taken is not handed back."""
        mgr = InstanceManager(base_mcp_port=3003)
        with patch.object(mgr, "_port_in_use", return_value=False):
            port = mgr.allocate_port()  # 3003
        mgr.release_port(port)
        # 3003 got taken by something else after release; skip it.
        with patch.object(mgr, "_port_in_use", side_effect=lambda p: p == 3003):
            assert mgr.allocate_port() == 3004


class TestInstanceManagerPortProbe:
    """Test the real socket-based port-availability probe (no stubbing)."""

    def test_port_in_use_detects_bound_socket(self):
        """_port_in_use returns True for a port held by a live listener."""
        mgr = InstanceManager()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
            held.bind(("127.0.0.1", 0))
            held.listen(1)
            taken = held.getsockname()[1]
            assert mgr._port_in_use(taken) is True
        # Once released, the same port reads as free.
        assert mgr._port_in_use(taken) is False


class TestInstanceManagerLifecycle:
    """Test instance registration lifecycle."""

    def test_manager_starts_empty(self):
        """Manager starts with no instances."""
        manager = InstanceManager()

        assert manager.list_instances() == []

    def test_register_and_get(self):
        """Can register and retrieve an instance."""
        mgr = InstanceManager()
        inst = CarlaInstance(name="guitar")
        mgr.register(inst)
        assert mgr.get("guitar") is inst

    def test_register_instance(self):
        """Can register an instance."""
        manager = InstanceManager()
        instance = CarlaInstance(name="main")

        manager.register(instance)

        assert "main" in manager.list_instances()

    def test_get_nonexistent_returns_none(self):
        """Getting nonexistent instance returns None."""
        manager = InstanceManager()

        assert manager.get("nonexistent") is None

    def test_unregister_instance(self):
        """Can unregister an instance."""
        manager = InstanceManager()
        instance = CarlaInstance(name="main")
        manager.register(instance)

        removed = manager.unregister("main")

        assert removed is instance
        assert manager.get("main") is None
