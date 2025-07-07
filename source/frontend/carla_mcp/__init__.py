"""
Carla MCP Server Module

This module provides Model Context Protocol (MCP) server functionality
integrated directly into the Carla frontend.
"""

from .main import start_mcp_server, stop_mcp_server, is_mcp_server_running

__version__ = "0.2.0"
__author__ = "Michael Biehl"
__description__ = "MCP server for comprehensive Carla audio plugin host control"
__all__ = ["start_mcp_server", "stop_mcp_server", "is_mcp_server_running"]