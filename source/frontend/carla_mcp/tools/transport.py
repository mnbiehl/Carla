"""
Transport control tools for Carla MCP Server

Tools for controlling audio transport (play, stop, tempo, etc.).
"""

from fastmcp import FastMCP
from ..backend.osc_client import CarlaOSCClient

# Global client instance - will be initialized in main.py
carla_client: CarlaOSCClient = None


def register_transport_tools(mcp: FastMCP, client: CarlaOSCClient):
    """Register transport control tools with the MCP server"""
    global carla_client
    carla_client = client
    
    # TODO: Implement transport control tools
    # - start_transport()
    # - stop_transport()
    # - set_bpm()
    # - get_transport_info()
    # - set_transport_position()
    pass