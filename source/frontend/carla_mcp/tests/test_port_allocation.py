"""Tests for dynamic port allocation starting at 3003.

Port 3002 is reserved for the looper MCP server, so effects chain
instances must start at 3003.
"""

from carla_mcp.state.instance_manager import InstanceManager


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
