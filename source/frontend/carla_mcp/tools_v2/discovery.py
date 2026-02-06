"""
Discovery tools for MCP.

These tools expose available ports, connections, and instances.
"""

from typing import Dict, List, Any
from ..state import StateManager, InstanceManager, JackDiscovery


def list_ports(state_manager: StateManager, jack_client: Any) -> Dict[str, List[str]]:
    """List all available JACK ports grouped by type.

    Returns:
        Dict with 'sources' (outputs) and 'destinations' (inputs)
    """
    discovery = JackDiscovery(jack_client)

    outputs = discovery.get_audio_outputs()
    inputs = discovery.get_audio_inputs()

    return {
        "sources": [p.name for p in outputs],
        "destinations": [p.name for p in inputs],
    }


def list_connections(state_manager: StateManager) -> List[Dict[str, str]]:
    """List all tracked connections.

    Returns:
        List of {"source": ..., "destination": ...} dicts
    """
    connections = state_manager.list_connections()
    return [{"source": src, "destination": dst} for src, dst in connections]


def list_instances(instance_manager: InstanceManager) -> List[Dict[str, Any]]:
    """List all Carla instances.

    Returns:
        List of instance info dicts
    """
    result = []
    for name in instance_manager.list_instances():
        instance = instance_manager.get(name)
        result.append({
            "name": name,
            "running": instance.is_running,
            "headless": instance.headless,
        })
    return result
