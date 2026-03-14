"""
Configuration module for Carla MCP Server

Contains default settings, environment variables, and configuration validation.
"""

import os
from typing import Optional

# Default Carla OSC settings
DEFAULT_OSC_HOST = "localhost"
DEFAULT_OSC_PORT = 19735

# Environment variable names
ENV_OSC_HOST = "CARLA_OSC_HOST"
ENV_OSC_PORT = "CARLA_OSC_UDP_PORT"

# Logging configuration
DEFAULT_LOG_LEVEL = "INFO"
ENV_LOG_LEVEL = "CARLA_MCP_LOG_LEVEL"

# MCP Server configuration
DEFAULT_MCP_HOST = "localhost"
DEFAULT_MCP_PORT = 3001
ENV_MCP_HOST = "CARLA_MCP_HOST"
ENV_MCP_PORT = "CARLA_MCP_PORT"

class CarlaConfig:
    """Configuration class for Carla MCP Server"""
    
    def __init__(self):
        self.osc_host = os.getenv(ENV_OSC_HOST, DEFAULT_OSC_HOST)
        self.osc_port = int(os.getenv(ENV_OSC_PORT, DEFAULT_OSC_PORT))
        self.log_level = os.getenv(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL)
        self.mcp_host = os.getenv(ENV_MCP_HOST, DEFAULT_MCP_HOST)
        self.mcp_port = int(os.getenv(ENV_MCP_PORT, DEFAULT_MCP_PORT))
    
    @property
    def osc_address(self) -> str:
        """Get the complete OSC address"""
        return f"{self.osc_host}:{self.osc_port}"
    
    @property
    def mcp_address(self) -> str:
        """Get the complete MCP server address"""
        return f"{self.mcp_host}:{self.mcp_port}"
    
    def validate(self) -> bool:
        """Validate configuration settings"""
        if not isinstance(self.osc_port, int) or not (1 <= self.osc_port <= 65535):
            return False
        if not isinstance(self.mcp_port, int) or not (1 <= self.mcp_port <= 65535):
            return False
        if not self.osc_host or not self.mcp_host:
            return False
        return True

# Global configuration instance
config = CarlaConfig()