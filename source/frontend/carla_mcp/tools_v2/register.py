"""
Register all v2 MCP tools with FastMCP server.

This replaces the old tool registration and uses the new state-aware tools.
"""

from typing import Any
from fastmcp import FastMCP

from ..state import StateManager, InstanceManager
from ..templates import TemplateManager
from .discovery import list_ports, list_connections, list_instances
from .routing import connect, disconnect
from .chains import create_chain, delete_chain


def register_v2_tools(
    mcp: FastMCP,
    state_manager: StateManager,
    instance_manager: InstanceManager,
    template_manager: TemplateManager,
    jack_client: Any
) -> None:
    """Register all v2 tools with the MCP server.

    Args:
        mcp: FastMCP server instance
        state_manager: Shared state manager
        instance_manager: Instance manager
        template_manager: Template manager
        jack_client: JACK client for audio routing
    """

    # Discovery tools

    @mcp.tool()
    def mcp_list_ports() -> dict:
        """List all available JACK audio ports.

        Returns grouped ports:
        - sources: Output ports (from loopers, plugins)
        - destinations: Input ports (plugin inputs, system playback)
        """
        return list_ports(state_manager, jack_client)

    @mcp.tool()
    def mcp_list_connections() -> list:
        """List all current audio connections.

        Returns list of {source, destination} pairs.
        """
        return list_connections(state_manager)

    @mcp.tool()
    def mcp_list_instances() -> list:
        """List all Carla instances.

        Returns info about each instance including running status.
        """
        return list_instances(instance_manager)

    # Routing tools

    @mcp.tool()
    def mcp_connect(source: str, destination: str, mode: str = "auto") -> dict:
        """Connect audio source to destination.

        Args:
            source: Source port name (exact or partial)
            destination: Destination port name (exact or partial)
            mode: Connection mode - "auto" (smart stereo), "left", "right"

        Returns:
            Result with success status. If partial names given, returns
            candidates for confirmation.
        """
        result = connect(state_manager, jack_client, source, destination, mode)
        return {
            "success": result.success,
            "message": result.message,
            "needs_confirmation": result.needs_confirmation,
            "source_matches": result.source_matches,
            "destination_matches": result.destination_matches,
        }

    @mcp.tool()
    def mcp_disconnect(source: str, destination: str) -> dict:
        """Disconnect audio source from destination.

        Args:
            source: Source port name
            destination: Destination port name
        """
        result = disconnect(state_manager, jack_client, source, destination)
        return {"success": result.success, "message": result.message}

    # Chain tools

    @mcp.tool()
    def mcp_create_chain(name: str, components: list, instance: str = "main") -> dict:
        """Create a named effects chain.

        Creates all connections between components in order.

        Args:
            name: Chain name
            components: Ordered list [source, plugin1, ..., destination]
            instance: Carla instance to use

        Example:
            create_chain("Guitar FX", ["looper:out_1", "Compressor", "Reverb", "system:playback"])
        """
        result = create_chain(state_manager, jack_client, name, components, instance)
        return {"success": result.success, "message": result.message}

    @mcp.tool()
    def mcp_delete_chain(name: str) -> dict:
        """Delete a chain and disconnect all its connections.

        Args:
            name: Chain name to delete
        """
        result = delete_chain(state_manager, jack_client, name)
        return {"success": result.success, "message": result.message}

    # Alias tools

    @mcp.tool()
    def mcp_create_alias(alias: str, target: str) -> dict:
        """Create an alias for a port name.

        Args:
            alias: Short name to use
            target: Full port name it refers to

        Example:
            create_alias("Guitar Loop", "looper:out_1")
        """
        state_manager.create_alias(alias, target)
        return {"success": True, "message": f"Created alias '{alias}' → '{target}'"}

    @mcp.tool()
    def mcp_remove_alias(alias: str) -> dict:
        """Remove an alias."""
        state_manager.remove_alias(alias)
        return {"success": True, "message": f"Removed alias '{alias}'"}

    @mcp.tool()
    def mcp_list_aliases() -> dict:
        """List all aliases."""
        return state_manager.list_aliases()

    # Template tools

    @mcp.tool()
    def mcp_save_template(name: str) -> dict:
        """Save current configuration as a template.

        Args:
            name: Template name
        """
        filepath = template_manager.save(name, state_manager)
        return {"success": True, "message": f"Saved template '{name}' to {filepath}"}

    @mcp.tool()
    def mcp_load_template(name: str, merge: bool = False) -> dict:
        """Load a saved template.

        Args:
            name: Template name
            merge: If true, merge with current state. Otherwise replace.
        """
        try:
            template_manager.apply(name, state_manager, merge=merge)
            return {"success": True, "message": f"Loaded template '{name}'"}
        except FileNotFoundError:
            return {"success": False, "message": f"Template '{name}' not found"}

    @mcp.tool()
    def mcp_list_templates() -> list:
        """List all saved templates."""
        return template_manager.list_templates()
