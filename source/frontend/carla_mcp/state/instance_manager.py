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
    headless: bool = True
    process: Optional[subprocess.Popen] = None
    host: Optional[Any] = None  # CarlaHostDLL when connected
    jack_client_name: Optional[str] = None

    @property
    def is_running(self) -> bool:
        """Check if the Carla process is running."""
        if self.process is None:
            return False
        return self.process.poll() is None


class InstanceManager:
    """Manages multiple Carla instances."""

    def __init__(self):
        self._instances: Dict[str, CarlaInstance] = {}

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
