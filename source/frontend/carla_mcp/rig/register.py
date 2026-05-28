"""Register MCP tools for the rig layer.

Each tool is a thin wrapper around a :class:`RigController` method.
Sync controller methods map to sync tool functions; async controller
methods map to ``async def`` tool functions that ``await`` the result.

Call :func:`register_rig_tools` once after constructing your controller
and ``FastMCP`` server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from carla_mcp.rig.controller import RigController
    from carla_mcp.rig.probe import RigProbe


def register_rig_tools(
    mcp: "FastMCP",
    controller: "RigController",
    probe: Optional["RigProbe"] = None,
) -> None:
    """Register all rig-layer MCP tools on *mcp*.

    Parameters
    ----------
    mcp:
        The :class:`FastMCP` server instance to register tools on.
    controller:
        The :class:`RigController` instance whose methods back each tool.
    probe:
        Optional :class:`RigProbe` for test-tone playback + level
        measurement.  When provided, three additional tools are
        registered: ``carla_play_tone``, ``carla_stop_tone``,
        ``carla_measure_level``.
    """

    @mcp.tool()
    def describe_rig() -> str:
        """Return a human/agent-readable ASCII summary of the current rig.

        Shows two sections: ROUTING (one line per audio edge) and CHAINS
        (one line per track/bus with its effects chain).  Use this to get
        situational awareness before making changes.
        """
        from carla_mcp.rig.describe import describe_rig as _describe
        return _describe(controller._graph)

    @mcp.tool()
    def create_track(name: str, source: str) -> dict:
        """Create a new track node wired from a named audio source.

        Launches a dedicated Carla effects-chain instance, auto-creates an
        endpoint node for *source* if it does not already exist, and
        immediately wires source audio into the track's input.

        Parameters
        ----------
        name:
            Stable identifier for the track (e.g. ``"strat"``).
        source:
            Port base or alias that feeds this track (e.g. ``"in:guitar"``).
        """
        return controller.create_track(name, source)

    @mcp.tool()
    def create_bus(name: str) -> dict:
        """Create a new bus node for effects sends or submixes.

        Launches a dedicated Carla effects-chain instance.  The bus has no
        source; route other nodes into it with :func:`route`.

        Parameters
        ----------
        name:
            Stable identifier for the bus (e.g. ``"reverb"``).
        """
        return controller.create_bus(name)

    @mcp.tool()
    def remove_node(name: str) -> dict:
        """Remove a node from the rig, terminating its Carla instance if any.

        All audio edges touching the node are removed from the graph.

        Parameters
        ----------
        name:
            Name of the node to remove.
        """
        return controller.remove_node(name)

    @mcp.tool()
    async def add_effect(
        node: str,
        plugin: str,
        role: str,
        position: str = "end",
    ) -> dict:
        """Add a plugin effect to a track or bus effects chain.

        Loads the plugin on the node's Carla child, stamps a stable handle,
        and rewires the chain.

        Parameters
        ----------
        node:
            Name of the target track or bus node.
        plugin:
            Plugin name or label to load (e.g. ``"LSP Compressor"``).
        role:
            Human role label, unique within this node (e.g. ``"comp"``).
        position:
            Insertion point — ``"end"``, ``"start"``, ``"before:<role>"``,
            ``"after:<role>"``, or an integer index string.  Defaults to
            ``"end"``.
        """
        return await controller.add_effect(node, plugin, role, position)

    @mcp.tool()
    async def remove_effect(node: str, effect: str) -> dict:
        """Remove an effect from a track or bus effects chain.

        Parameters
        ----------
        node:
            Name of the target track or bus node.
        effect:
            The effect's role or stable handle to remove.
        """
        return await controller.remove_effect(node, effect)

    @mcp.tool()
    async def move_effect(node: str, effect: str, position: str) -> dict:
        """Move an existing effect to a new position in a track or bus chain.

        Parameters
        ----------
        node:
            Name of the target track or bus node.
        effect:
            The effect's role or stable handle to move.
        position:
            Target position — ``"end"``, ``"start"``, ``"before:<role>"``,
            ``"after:<role>"``, or an integer index string.
        """
        return await controller.move_effect(node, effect, position)

    @mcp.tool()
    async def set_param(
        node: str,
        effect: str,
        param: str,
        value: float,
    ) -> dict:
        """Set a named parameter on an effect in a track or bus chain.

        Parameters
        ----------
        node:
            Name of the target track or bus node.
        effect:
            The effect's role or stable handle.
        param:
            Parameter name to set (case-insensitive).
        value:
            New parameter value in the plugin's native unit.
        """
        return await controller.set_param(node, effect, param, value)

    @mcp.tool()
    async def bypass(node: str, effect: str, on: bool = True) -> dict:
        """Bypass or un-bypass an effect in a track or bus chain.

        Parameters
        ----------
        node:
            Name of the target track or bus node.
        effect:
            The effect's role or stable handle.
        on:
            ``True`` to bypass (disable) the effect; ``False`` to un-bypass.
        """
        return await controller.bypass(node, effect, on)

    @mcp.tool()
    def route(src: str, dst: str) -> dict:
        """Wire audio from *src* to *dst* via pw-link and record the graph edge.

        Auto-creates endpoint nodes for names not yet in the graph (e.g.
        ``"out:main"``).

        Parameters
        ----------
        src:
            Name of the source node or endpoint.
        dst:
            Name of the destination node or endpoint.
        """
        return controller.route(src, dst)

    @mcp.tool()
    def unroute(src: str, dst: str) -> dict:
        """Remove an audio connection from *src* to *dst* and update the graph.

        Parameters
        ----------
        src:
            Name of the source node.
        dst:
            Name of the destination node.
        """
        return controller.unroute(src, dst)

    @mcp.tool()
    def list_io() -> dict:
        """Discover available audio sources, sinks, and current endpoint aliases.

        Returns a snapshot of what is visible on PipeWire plus the friendly
        names already registered in the rig graph as endpoint nodes.  Use
        this before creating tracks to find valid *source* values.

        Returns a dict with keys:
          - ``sources``: JACK output ports available as track inputs.
          - ``sinks``: PipeWire input ports / monitor outputs.
          - ``aliases``: ``{name: port}`` for registered endpoint nodes.
        """
        return controller.list_io()

    @mcp.tool()
    def alias_input(port: str, name: str) -> dict:
        """Register a friendly endpoint alias for a raw JACK port.

        Creates an endpoint node so that ``route(name, ...)`` resolves to
        *port*.  Use this to give human-readable names to hardware inputs
        before building tracks.

        Parameters
        ----------
        port:
            Raw JACK port string (e.g. ``"alsa_input.usb:capture_AUX0"``).
        name:
            Friendly alias to register (e.g. ``"in:guitar"``).
        """
        return controller.alias_input(port, name)

    @mcp.tool()
    def find_plugins(query: str = "", category: str = "") -> dict:
        """Search available plugins in the plugin database.

        Parameters
        ----------
        query:
            Case-insensitive substring to match against plugin name, label,
            or maker.  Empty string returns all plugins.
        category:
            Exact (case-insensitive) category filter.  Empty string means
            no category filter.

        Returns a dict with keys:
          - ``success``: whether the lookup succeeded.
          - ``plugins``: list of plugin info dicts (up to 50 results).
        """
        return controller.find_plugins(
            query=query if query else None,
            category=category if category else None,
        )

    # ----- Probe tools (optional) -----------------------------------------
    if probe is None:
        return

    @mcp.tool()
    async def play_tone(
        node: str,
        hz: float = 440.0,
        db: float = -12.0,
        at: str = "input",
    ) -> dict:
        """Play a mono sine tone into *node*'s input or output port.

        Use to validate signal flow without human ears.  Pair with
        :func:`measure_level` at another node to check whether signal
        actually passes through the chain.

        Parameters
        ----------
        node:
            Name of the target node in the rig graph.
        hz:
            Tone frequency in Hz (default 440).
        db:
            Tone peak amplitude in dBFS (default -12).
        at:
            ``"input"`` (default) or ``"output"`` — which side of the
            node to inject the tone at.
        """
        return await probe.play_tone(node, hz=hz, db=db, at=at)

    @mcp.tool()
    def stop_tone(node: str) -> dict:
        """Stop any test tone currently playing on *node*.

        Parameters
        ----------
        node:
            Name of the node whose tone should be stopped.
        """
        return probe.stop_tone(node)

    @mcp.tool()
    async def measure_level(
        node: str,
        at: str = "output",
        duration: float = 0.5,
    ) -> dict:
        """Capture *node*'s input or output for *duration* s and report dBFS.

        Returns peak and RMS levels in dBFS (floored at -120).  Pair
        with :func:`play_tone` to verify signal flow.

        Parameters
        ----------
        node:
            Name of the node to measure.
        at:
            ``"output"`` (default) or ``"input"``.
        duration:
            Capture duration in seconds (default 0.5).
        """
        return await probe.measure_level(node, at=at, duration=duration)
