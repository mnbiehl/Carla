"""
Session management tools for Carla MCP Server

Tools for managing Carla sessions and project files.
"""

from fastmcp import FastMCP
from ..backend.osc_client import CarlaOSCClient

# Global client instance - will be initialized in main.py
carla_client: CarlaOSCClient = None


def register_session_tools(mcp: FastMCP, client: CarlaOSCClient):
    """Register session management tools with the MCP server"""
    global carla_client
    carla_client = client
    
    # TODO: Implement session management tools
    # - save_project()
    # - load_project()
    # - export_plugin_state()
    # - import_plugin_state()
    # - get_project_info()
    pass