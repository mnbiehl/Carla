"""Tests for multi-instance Carla management."""

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

    def test_allocates_sequential_ports(self):
        """Ports are allocated sequentially from base."""
        mgr = InstanceManager(base_mcp_port=3002)
        assert mgr.allocate_port() == 3002
        assert mgr.allocate_port() == 3003

    def test_reclaims_released_ports(self):
        """Released ports are reused before allocating new ones."""
        mgr = InstanceManager(base_mcp_port=3002)
        port = mgr.allocate_port()
        mgr.release_port(port)
        assert mgr.allocate_port() == 3002

    def test_release_then_allocate_multiple(self):
        """Multiple released ports are all reusable."""
        mgr = InstanceManager(base_mcp_port=3002)
        p1 = mgr.allocate_port()
        p2 = mgr.allocate_port()
        mgr.release_port(p1)
        mgr.release_port(p2)
        reclaimed = {mgr.allocate_port(), mgr.allocate_port()}
        assert reclaimed == {3002, 3003}

    def test_default_base_port(self):
        """Default base port is 3002."""
        mgr = InstanceManager()
        assert mgr.allocate_port() == 3002


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
