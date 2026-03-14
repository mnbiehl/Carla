"""
JACK port discovery.

Wraps JACK client to discover available audio ports.
"""

from dataclasses import dataclass
from typing import List, Optional, Any


@dataclass
class PortInfo:
    """Information about a JACK port."""

    name: str  # Full name: "client:port"
    client: str  # Client name
    port: str  # Port name within client
    is_input: bool
    is_audio: bool
    is_midi: bool = False


class JackDiscovery:
    """Discovers JACK ports."""

    def __init__(self, jack_client: Any):
        """Initialize with a JACK client.

        Args:
            jack_client: A jack.Client instance or mock
        """
        self._client = jack_client

    def _port_to_info(self, port: Any) -> PortInfo:
        """Convert JACK port object to PortInfo."""
        name = str(port.name)
        client, port_name = name.split(":", 1) if ":" in name else (name, "")

        return PortInfo(
            name=name,
            client=client,
            port=port_name,
            is_input=port.is_input,
            is_audio=port.is_audio,
            is_midi=getattr(port, "is_midi", False)
        )

    def get_all_ports(self) -> List[PortInfo]:
        """Get all JACK ports."""
        ports = self._client.get_ports()
        return [self._port_to_info(p) for p in ports]

    def get_audio_outputs(self) -> List[PortInfo]:
        """Get all audio output ports."""
        ports = self._client.get_ports()
        return [
            self._port_to_info(p) for p in ports
            if p.is_audio and not p.is_input
        ]

    def get_audio_inputs(self) -> List[PortInfo]:
        """Get all audio input ports."""
        ports = self._client.get_ports()
        return [
            self._port_to_info(p) for p in ports
            if p.is_audio and p.is_input
        ]

    def get_client_ports(self, client_name: str) -> List[PortInfo]:
        """Get all ports for a specific JACK client."""
        all_ports = self.get_all_ports()
        return [p for p in all_ports if p.client == client_name]
