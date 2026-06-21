"""Tests for dynamic port allocation starting at 3003.

Port 3002 is reserved for the looper MCP server, so effects chain
instances must start at 3003.
"""

from unittest.mock import patch

import pytest

from carla_mcp.state.instance_manager import InstanceManager


@pytest.fixture(autouse=True)
def _all_ports_free():
    """Treat every candidate port as free so allocation is deterministic.

    allocate_port() bind-tests each port; stub the probe so these tests stay
    independent of whatever is bound on the test host.
    """
    with patch.object(InstanceManager, "_port_in_use", return_value=False):
        yield


def test_first_port_is_3003():
    manager = InstanceManager()
    assert manager.allocate_port() == 3003


def test_ports_increment():
    manager = InstanceManager()
    assert manager.allocate_port() == 3003
    assert manager.allocate_port() == 3004
    assert manager.allocate_port() == 3005


def test_released_port_reused():
    manager = InstanceManager()
    p1 = manager.allocate_port()  # 3003
    p2 = manager.allocate_port()  # 3004
    manager.release_port(p1)
    assert manager.allocate_port() == 3003  # reused
