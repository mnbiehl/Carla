"""
Chain builder tool for Carla MCP Server

Provides a single MCP tool to add multiple plugins and wire them in series
with auto-detected mono/stereo routing.
"""

import json
from typing import List, Dict, Tuple
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge
from ..constants import (
    PATCHBAY_PORT_AUDIO_INPUT_OFFSET,
    PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET,
)
from ..utils.pw_link import ensure_carla_to_monitors


def _make_connections(
    bridge: CarlaBackendBridge,
    src_plugin_id: int,
    src_group: int,
    dst_plugin_id: int,
    dst_group: int,
) -> List[Tuple[int, int, int, int]]:
    """Determine patchbay connections between two plugins based on channel counts.

    Returns a list of (group_a, port_a, group_b, port_b) tuples.
    """
    _, src_outs = bridge.get_audio_port_counts(src_plugin_id)
    dst_ins, _ = bridge.get_audio_port_counts(dst_plugin_id)

    src_is_mono = src_outs <= 1
    dst_is_mono = dst_ins <= 1

    connections = []
    if src_is_mono and dst_is_mono:
        # mono -> mono: 1 connection
        connections.append((
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
    elif src_is_mono and not dst_is_mono:
        # mono -> stereo: duplicate output to both inputs
        connections.append((
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
        connections.append((
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        ))
    elif not src_is_mono and dst_is_mono:
        # stereo -> mono: sum both outputs to input 0
        connections.append((
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
        connections.append((
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
    else:
        # stereo -> stereo: L->L, R->R
        connections.append((
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
        connections.append((
            src_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            dst_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        ))

    return connections


def _make_system_to_plugin_connections(
    bridge: CarlaBackendBridge,
    plugin_id: int,
    plugin_group: int,
    system_group: int,
) -> List[Tuple[int, int, int, int]]:
    """Determine connections from system input to a plugin."""
    dst_ins, _ = bridge.get_audio_port_counts(plugin_id)
    dst_is_mono = dst_ins <= 1

    connections = []
    if dst_is_mono:
        connections.append((
            system_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            plugin_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
    else:
        # Stereo: L->L, R->R from system
        connections.append((
            system_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            plugin_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
        connections.append((
            system_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            plugin_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        ))
    return connections


def _make_plugin_to_system_connections(
    bridge: CarlaBackendBridge,
    plugin_id: int,
    plugin_group: int,
    system_group: int,
) -> List[Tuple[int, int, int, int]]:
    """Determine connections from a plugin to system output."""
    _, src_outs = bridge.get_audio_port_counts(plugin_id)
    src_is_mono = src_outs <= 1

    connections = []
    if src_is_mono:
        # Mono: duplicate to both system inputs
        connections.append((
            plugin_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            system_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
        connections.append((
            plugin_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            system_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        ))
    else:
        # Stereo: L->L, R->R
        connections.append((
            plugin_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
            system_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0,
        ))
        connections.append((
            plugin_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
            system_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1,
        ))
    return connections


def _make_system_to_system_connections(
    bridge: CarlaBackendBridge,
) -> List[Tuple[int, int, int, int]]:
    """Direct dry passthrough: instance input (group 1) → output (group 2).

    Used when a chain has no plugins to wire (e.g. every effect bypassed) so
    the node still passes audio dry instead of going silent.  Wires the stereo
    pair L->L, R->R.  Verified live: a -12 dBFS tone into audio-in1 emerges at
    audio-out1 at -12 dBFS with this wiring.
    """
    return [
        (1, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0, 2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0),
        (1, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1, 2, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1),
    ]


def build_chain(
    bridge: CarlaBackendBridge,
    plugins: List[str],
    connect_system_input: bool = False,
    connect_system_output: bool = False,
) -> dict:
    """Add a list of plugins and wire them in series.

    Args:
        bridge: The Carla backend bridge instance.
        plugins: List of plugin names to add in order.
        connect_system_input: Wire system audio input (group 1) to first plugin.
        connect_system_output: Wire last plugin to system audio output (group 2).

    Returns:
        Dict with keys: success, plugins, connections, error.
    """
    added_plugin_ids: List[int] = []
    all_connections: List[Tuple[int, int, int, int]] = []

    # Phase 1: Add all plugins
    for name in plugins:
        current_count = bridge.get_plugin_count()
        success, msg = bridge.add_plugin_by_name(name)
        if not success:
            # Rollback: remove already-added plugins in reverse order
            for pid in reversed(added_plugin_ids):
                bridge.remove_plugin(pid)
            return {
                "success": False,
                "plugins": [],
                "connections": [],
                "error": f"Failed to add plugin '{name}': {msg}",
            }
        added_plugin_ids.append(current_count)

    # Phase 2: Wire adjacent plugins
    for i in range(len(added_plugin_ids) - 1):
        src_id = added_plugin_ids[i]
        dst_id = added_plugin_ids[i + 1]
        src_group = bridge._plugin_to_group_map[src_id]
        dst_group = bridge._plugin_to_group_map[dst_id]

        conns = _make_connections(bridge, src_id, src_group, dst_id, dst_group)
        for ga, pa, gb, pb in conns:
            bridge.patchbay_connect(ga, pa, gb, pb)
            all_connections.append((ga, pa, gb, pb))

    # Phase 3: Optional system I/O
    if connect_system_input and added_plugin_ids:
        first_id = added_plugin_ids[0]
        first_group = bridge._plugin_to_group_map[first_id]
        conns = _make_system_to_plugin_connections(bridge, first_id, first_group, 1)
        for ga, pa, gb, pb in conns:
            bridge.patchbay_connect(ga, pa, gb, pb)
            all_connections.append((ga, pa, gb, pb))

    if connect_system_output and added_plugin_ids:
        last_id = added_plugin_ids[-1]
        last_group = bridge._plugin_to_group_map[last_id]
        conns = _make_plugin_to_system_connections(bridge, last_id, last_group, 2)
        for ga, pa, gb, pb in conns:
            bridge.patchbay_connect(ga, pa, gb, pb)
            all_connections.append((ga, pa, gb, pb))

    result = {
        "success": True,
        "plugins": [
            {"id": pid, "name": name}
            for pid, name in zip(added_plugin_ids, plugins)
        ],
        "connections": [
            {"group_a": ga, "port_a": pa, "group_b": gb, "port_b": pb}
            for ga, pa, gb, pb in all_connections
        ],
        "error": None,
    }

    # Phase 4: Auto-wire external monitors if system output connected
    if connect_system_output and added_plugin_ids:
        result["external_monitors"] = ensure_carla_to_monitors()

    return result


def rewire_chain_connections(bridge: CarlaBackendBridge, plugin_ids: List[int]) -> dict:
    """Disconnect all existing internal connections and rewire to the given plugin order.

    Removes every currently-tracked (non-pending) internal connection, then
    re-wires system-in → plugin_ids[0] → … → plugin_ids[-1] → system-out.

    Args:
        bridge:     The Carla backend bridge for the child instance.
        plugin_ids: Ordered list of plugin IDs for the new chain.

    Returns:
        ``{"success": True, "plugin_order": plugin_ids, "connections": <count>}``
        on success, or ``{"success": False, "error": <message>}`` on exception.
    """
    try:
        # Step 1: disconnect all currently-tracked internal connections
        for conn in bridge.get_patchbay_connections():
            bridge.patchbay_disconnect(conn["id"])

        # Step 2: if no plugins remain (e.g. every effect bypassed), wire the
        # instance input straight to its output so the node passes signal dry
        # instead of going silent.
        if not plugin_ids:
            count = 0
            for ga, pa, gb, pb in _make_system_to_system_connections(bridge):
                bridge.patchbay_connect(ga, pa, gb, pb)
                count += 1
            return {"success": True, "plugin_order": plugin_ids, "connections": count}

        connection_count = 0

        # Step 3: wire system input (group 1) → first plugin
        first_id = plugin_ids[0]
        first_group = bridge._plugin_to_group_map[first_id]
        for ga, pa, gb, pb in _make_system_to_plugin_connections(bridge, first_id, first_group, 1):
            bridge.patchbay_connect(ga, pa, gb, pb)
            connection_count += 1

        # Step 4: wire adjacent pairs
        for i in range(len(plugin_ids) - 1):
            pid_i = plugin_ids[i]
            pid_next = plugin_ids[i + 1]
            group_i = bridge._plugin_to_group_map[pid_i]
            group_next = bridge._plugin_to_group_map[pid_next]
            for ga, pa, gb, pb in _make_connections(bridge, pid_i, group_i, pid_next, group_next):
                bridge.patchbay_connect(ga, pa, gb, pb)
                connection_count += 1

        # Step 5: wire last plugin → system output (group 2)
        last_id = plugin_ids[-1]
        last_group = bridge._plugin_to_group_map[last_id]
        for ga, pa, gb, pb in _make_plugin_to_system_connections(bridge, last_id, last_group, 2):
            bridge.patchbay_connect(ga, pa, gb, pb)
            connection_count += 1

        return {"success": True, "plugin_order": plugin_ids, "connections": connection_count}

    except Exception as exc:
        return {"success": False, "error": str(exc)}


def register_chain_builder_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register the build_effects_chain and rewire_chain MCP tools."""

    @mcp.tool()
    def rewire_chain(plugin_ids: List[int]) -> str:
        """Rewire the internal chain of this child instance to the given plugin order.

        Disconnects all existing internal patchbay connections, then re-wires
        system-in → plugin_ids[0] → … → plugin_ids[-1] → system-out using
        auto-detected mono/stereo routing.

        Args:
            plugin_ids: Ordered list of current Carla plugin IDs for the chain.

        Returns:
            JSON result with success status, plugin_order, and connections count.
        """
        if not bridge:
            return json.dumps({"success": False, "error": "Backend not available"})

        result = rewire_chain_connections(bridge, plugin_ids)
        return json.dumps(result)

    @mcp.tool()
    def build_effects_chain(
        plugins: List[str],
        connect_system_input: bool = False,
        connect_system_output: bool = False,
    ) -> str:
        """
        Build a complete effects chain in one call.

        Adds all listed plugins and wires them in series with auto-detected
        mono/stereo routing. Optionally connects system audio I/O.

        If any plugin fails to load, all previously added plugins are removed
        (rollback).

        Args:
            plugins: List of plugin names to add in chain order.
            connect_system_input: Connect system audio input to first plugin.
            connect_system_output: Connect last plugin to system audio output.

        Returns:
            JSON result with success status, plugin IDs, and connections made.
        """
        if not bridge:
            return json.dumps({"success": False, "error": "Backend not available"})

        if not plugins:
            return json.dumps({"success": False, "error": "No plugins specified"})

        result = build_chain(
            bridge,
            plugins,
            connect_system_input=connect_system_input,
            connect_system_output=connect_system_output,
        )
        return json.dumps(result, indent=2)
