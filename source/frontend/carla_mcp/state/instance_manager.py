"""
Multi-instance Carla management.

Each Carla instance runs as a separate process for parallel processing.
The InstanceManager tracks and controls all instances.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import subprocess


@dataclass
class CarlaInstance:
    """Represents a single Carla process."""

    name: str
    headless: bool = False
    process: Optional[subprocess.Popen] = None
    host: Optional[Any] = None  # CarlaHostDLL when connected
    jack_client_name: Optional[str] = None
    mcp_port: Optional[int] = None

    @property
    def is_running(self) -> bool:
        """Check if the Carla process is running."""
        if self.process is None:
            return False
        return self.process.poll() is None


class InstanceManager:
    """Manages multiple Carla instances."""

    def __init__(self, base_mcp_port: int = 3003):
        self._instances: Dict[str, CarlaInstance] = {}
        self._base_mcp_port = base_mcp_port
        self._next_port = base_mcp_port
        self._released_ports: List[int] = []

    def allocate_port(self) -> int:
        """Allocate next available MCP port, reusing released ports first."""
        if self._released_ports:
            return self._released_ports.pop(0)
        port = self._next_port
        self._next_port += 1
        return port

    def release_port(self, port: int) -> None:
        """Release a port for reuse."""
        if port not in self._released_ports:
            self._released_ports.append(port)

    def register(self, instance: CarlaInstance) -> None:
        """Register an instance."""
        self._instances[instance.name] = instance

    def unregister(self, name: str) -> Optional[CarlaInstance]:
        """Unregister and return an instance."""
        return self._instances.pop(name, None)

    def get(self, name: str) -> Optional[CarlaInstance]:
        """Get instance by name."""
        return self._instances.get(name)

    def list_instances(self) -> List[str]:
        """List all instance names."""
        return list(self._instances.keys())

    def get_running(self) -> List[CarlaInstance]:
        """Get all running instances."""
        return [i for i in self._instances.values() if i.is_running]
