"""Tests for multi-instance Carla management."""

import pytest
from unittest.mock import Mock, patch
from carla_mcp.state.instance_manager import CarlaInstance, InstanceManager


class TestCarlaInstance:
    """Test CarlaInstance data structure."""

    def test_instance_creation(self):
        """Can create instance with name."""
        instance = CarlaInstance(name="main", headless=True)

        assert instance.name == "main"
        assert instance.headless is True
        assert instance.process is None
        assert instance.host is None

    def test_instance_not_running_initially(self):
        """New instance is not running."""
        instance = CarlaInstance(name="test", headless=True)

        assert not instance.is_running


class TestInstanceManager:
    """Test InstanceManager operations."""

    def test_manager_starts_empty(self):
        """Manager starts with no instances."""
        manager = InstanceManager()

        assert manager.list_instances() == []

    def test_register_instance(self):
        """Can register an instance."""
        manager = InstanceManager()
        instance = CarlaInstance(name="main", headless=True)

        manager.register(instance)

        assert "main" in manager.list_instances()

    def test_get_instance(self):
        """Can retrieve instance by name."""
        manager = InstanceManager()
        instance = CarlaInstance(name="main", headless=True)
        manager.register(instance)

        retrieved = manager.get("main")

        assert retrieved is instance

    def test_get_nonexistent_returns_none(self):
        """Getting nonexistent instance returns None."""
        manager = InstanceManager()

        assert manager.get("nonexistent") is None
