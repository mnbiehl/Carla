"""
Configuration for Carla MCP Dispatcher
"""

import os
from pathlib import Path
from typing import Optional


class DispatcherConfig:
    """Configuration for the dispatcher"""
    
    def __init__(self):
        # Dispatcher server settings
        self.dispatcher_port = int(os.getenv("CARLA_DISPATCHER_PORT", "3000"))
        
        # Instance settings
        self.max_instances = int(os.getenv("CARLA_MAX_INSTANCES", "16"))
        self.base_mcp_port = int(os.getenv("CARLA_BASE_MCP_PORT", "3010"))
        
        # Carla executable path
        self.carla_executable = os.getenv("CARLA_EXECUTABLE", "")
        
        # Logging
        self.log_level = os.getenv("CARLA_DISPATCHER_LOG_LEVEL", "INFO")
        
        # Instance defaults
        self.default_channels = int(os.getenv("CARLA_DEFAULT_CHANNELS", "2"))
        
        # Timeouts
        self.startup_timeout = float(os.getenv("CARLA_STARTUP_TIMEOUT", "10.0"))
        self.shutdown_timeout = float(os.getenv("CARLA_SHUTDOWN_TIMEOUT", "5.0"))
    
    def validate(self) -> bool:
        """Validate configuration"""
        if self.dispatcher_port < 1 or self.dispatcher_port > 65535:
            return False
        
        if self.base_mcp_port < 1 or self.base_mcp_port > 65535:
            return False
        
        if self.max_instances < 1:
            return False
        
        # Check port range doesn't overlap
        max_port = self.base_mcp_port + self.max_instances
        if max_port > 65535:
            return False
        
        return True