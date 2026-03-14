"""
Routing tools for MCP.

Connect and disconnect audio ports with stereo awareness.
"""

from dataclasses import dataclass, field
from typing import List, Any, Optional
from ..state import StateManager, NameMatcher, JackDiscovery, get_stereo_pair, get_channel_type


@dataclass
class ConnectResult:
    """Result of a connect/disconnect operation."""

    success: bool
    message: str
    needs_confirmation: bool = False
    source_matches: List[str] = field(default_factory=list)
    destination_matches: List[str] = field(default_factory=list)


def connect(
    state_manager: StateManager,
    jack_client: Any,
    source: str,
    destination: str,
    mode: Optional[str] = None
) -> ConnectResult:
    """Connect source to destination.

    Args:
        state_manager: State manager instance
        jack_client: JACK client for making connections
        source: Source port name (exact or partial)
        destination: Destination port name (exact or partial)
        mode: "auto" (smart stereo), "left", "right", "sum", "duplicate", or None to ask for confirmation

    Returns:
        ConnectResult with success status or candidates for confirmation
    """
    source = state_manager.resolve_name(source)
    destination = state_manager.resolve_name(destination)

    discovery = JackDiscovery(jack_client)
    outputs = [p.name for p in discovery.get_audio_outputs()]
    inputs = [p.name for p in discovery.get_audio_inputs()]

    source_matcher = NameMatcher(outputs)
    source_result = source_matcher.match(source)

    dest_matcher = NameMatcher(inputs)
    dest_result = dest_matcher.match(destination)

    if not source_result.matches:
        return ConnectResult(
            success=False,
            message=f"No source port matching '{source}' found"
        )
    if not dest_result.matches:
        return ConnectResult(
            success=False,
            message=f"No destination port matching '{destination}' found"
        )

    # In auto mode, allow multiple matches since we can resolve stereo pairs
    if mode == "auto":
        # For auto mode, use the common base (before _L/_R)
        src_base = source if not source_result.is_exact else source_result.matches[0]
        dst_base = destination if not dest_result.is_exact else dest_result.matches[0]

        return _connect_auto(
            state_manager, jack_client,
            src_base,
            dst_base,
            outputs, inputs
        )

    # For other modes or no mode, require exact matches or ask for confirmation
    if source_result.needs_confirmation or dest_result.needs_confirmation:
        return ConnectResult(
            success=False,
            message="Multiple matches found. Please specify exact port names.",
            needs_confirmation=True,
            source_matches=source_result.matches,
            destination_matches=dest_result.matches
        )

    src_port = source_result.matches[0]
    dst_port = dest_result.matches[0]

    try:
        jack_client.connect(src_port, dst_port)
        state_manager.add_connection(src_port, dst_port)
        return ConnectResult(
            success=True,
            message=f"Connected {src_port} → {dst_port}"
        )
    except Exception as e:
        return ConnectResult(
            success=False,
            message=f"Connection failed: {e}"
        )


def _connect_auto(
    state_manager: StateManager,
    jack_client: Any,
    source: str,
    destination: str,
    available_outputs: List[str],
    available_inputs: List[str]
) -> ConnectResult:
    """Auto-connect with stereo pair detection."""
    # Try with uppercase L/R
    source_l = f"{source}_L"
    source_r = f"{source}_R"
    dest_l = f"{destination}_L"
    dest_r = f"{destination}_R"

    has_stereo_source = source_l in available_outputs and source_r in available_outputs
    has_stereo_dest = dest_l in available_inputs and dest_r in available_inputs

    connections_made = []

    if has_stereo_source and has_stereo_dest:
        try:
            jack_client.connect(source_l, dest_l)
            state_manager.add_connection(source_l, dest_l)
            connections_made.append(f"{source_l} → {dest_l}")

            jack_client.connect(source_r, dest_r)
            state_manager.add_connection(source_r, dest_r)
            connections_made.append(f"{source_r} → {dest_r}")

            return ConnectResult(
                success=True,
                message=f"Connected stereo pair: {', '.join(connections_made)}"
            )
        except Exception as e:
            return ConnectResult(success=False, message=f"Stereo connection failed: {e}")

    # Try with lowercase l/r
    source_l_lower = f"{source}_l"
    source_r_lower = f"{source}_r"
    dest_l_lower = f"{destination}_l"
    dest_r_lower = f"{destination}_r"

    has_stereo_source_lower = source_l_lower in available_outputs and source_r_lower in available_outputs
    has_stereo_dest_lower = dest_l_lower in available_inputs and dest_r_lower in available_inputs

    if has_stereo_source_lower and has_stereo_dest_lower:
        try:
            jack_client.connect(source_l_lower, dest_l_lower)
            state_manager.add_connection(source_l_lower, dest_l_lower)
            connections_made.append(f"{source_l_lower} → {dest_l_lower}")

            jack_client.connect(source_r_lower, dest_r_lower)
            state_manager.add_connection(source_r_lower, dest_r_lower)
            connections_made.append(f"{source_r_lower} → {dest_r_lower}")

            return ConnectResult(
                success=True,
                message=f"Connected stereo pair: {', '.join(connections_made)}"
            )
        except Exception as e:
            return ConnectResult(success=False, message=f"Stereo connection failed: {e}")

    if source in available_outputs and destination in available_inputs:
        try:
            jack_client.connect(source, destination)
            state_manager.add_connection(source, destination)
            return ConnectResult(success=True, message=f"Connected {source} → {destination}")
        except Exception as e:
            return ConnectResult(success=False, message=f"Connection failed: {e}")

    return ConnectResult(
        success=False,
        message=f"Could not find exact ports for '{source}' → '{destination}'"
    )


def disconnect(
    state_manager: StateManager,
    jack_client: Any,
    source: str,
    destination: str
) -> ConnectResult:
    """Disconnect source from destination."""
    source = state_manager.resolve_name(source)
    destination = state_manager.resolve_name(destination)

    try:
        jack_client.disconnect(source, destination)
        state_manager.remove_connection(source, destination)
        return ConnectResult(
            success=True,
            message=f"Disconnected {source} → {destination}"
        )
    except Exception as e:
        return ConnectResult(
            success=False,
            message=f"Disconnect failed: {e}"
        )
