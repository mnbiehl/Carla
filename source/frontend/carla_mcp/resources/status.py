"""
Status resources for Carla MCP Server

Resources for monitoring connection status and system information.
"""

import json
import time
from fastmcp import FastMCP
from ..backend.osc_client import CarlaOSCClient

# Global client instance - will be initialized in main.py
carla_client: CarlaOSCClient = None


def register_status_resources(mcp: FastMCP, client: CarlaOSCClient):
    """Register status monitoring resources with the MCP server"""
    global carla_client
    carla_client = client
    
    @mcp.resource("carla://status")
    def get_carla_status() -> str:
        """Get the current status of the Carla OSC connection"""
        status = {
            "osc_host": carla_client.host,
            "osc_port": carla_client.port,
            "connection_test": carla_client.test_connection(),
            "timestamp": time.time()
        }
        return json.dumps(status, indent=2)