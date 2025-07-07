"""
Parameter control tools for Carla MCP Server

Tools for manipulating plugin parameters and settings.
"""

from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_parameter_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register parameter control tools with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    @mcp.tool()
    def set_plugin_parameter(plugin_id: int, parameter_id: int, value: float) -> str:
        """
        Set a parameter value for a plugin in Carla
        
        Args:
            plugin_id: The ID of the plugin (0-based index)
            parameter_id: The parameter ID within the plugin
            value: Parameter value (typically 0.0 to 1.0, but depends on parameter)
        """
        if not backend_bridge.is_engine_running():
            return "❌ Cannot set parameter: Carla engine is not running"
        
        if backend_bridge.set_parameter_value(plugin_id, parameter_id, value):
            return f"✅ Set plugin {plugin_id} parameter {parameter_id} to {value:.3f}"
        else:
            return f"❌ Failed to set plugin {plugin_id} parameter {parameter_id}"