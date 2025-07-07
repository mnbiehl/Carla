"""
Backend module for Carla MCP Server

Provides client classes for communicating with Carla audio host through
OSC protocol and direct backend API.
"""

from .osc_client import CarlaOSCClient
from .carla_client import CarlaBackendClient, CARLA_BACKEND_AVAILABLE

__all__ = ['CarlaOSCClient', 'CarlaBackendClient', 'CARLA_BACKEND_AVAILABLE']