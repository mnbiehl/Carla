"""
Monitoring resources for Carla MCP Server

Resources for real-time monitoring of audio levels, performance, and transport.
"""

from fastmcp import FastMCP
from ..backend.osc_client import CarlaOSCClient

# Global client instance - will be initialized in main.py
carla_client: CarlaOSCClient = None


def register_monitoring_resources(mcp: FastMCP, client: CarlaOSCClient):
    """Register real-time monitoring resources with the MCP server"""
    global carla_client
    carla_client = client
    
    # TODO: Implement real-time monitoring resources
    # - get_transport_status() (live transport info)
    # - get_audio_levels() (peak meters)
    # - get_plugin_status() (live plugin monitoring)
    # - get_performance_stats() (CPU/DSP usage)
    pass