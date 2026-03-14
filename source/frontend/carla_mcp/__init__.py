"""
Carla MCP Server Module

This module provides Model Context Protocol (MCP) server functionality
integrated directly into the Carla frontend.
"""

__version__ = "0.2.0"
__author__ = "Michael Biehl"
__description__ = "MCP server for comprehensive Carla audio plugin host control"

# Lazy imports to avoid issues with carla_backend compatibility
try:
    from .main import start_mcp_server, stop_mcp_server, is_mcp_server_running
    __all__ = ["start_mcp_server", "stop_mcp_server", "is_mcp_server_running"]
except ImportError:
    # In testing environments, carla_backend may have incompatibilities
    # Tests should import specific modules directly
    __all__ = []