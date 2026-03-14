"""
Session management tools for Carla MCP Server

Tools for managing Carla sessions and project files.
"""

import os
from typing import Optional
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_session_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register session management tools with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    @mcp.tool()
    def save_project(filename: str) -> str:
        """
        Save current Carla session as a project file
        
        Args:
            filename: Path where to save the project file (should end with .carxp)
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend bridge not available"
        
        # Ensure .carxp extension
        if not filename.endswith('.carxp'):
            filename += '.carxp'
        
        # Create directory if it doesn't exist
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except Exception as e:
                return f"❌ Failed to create directory: {e}"
        
        if backend_bridge.save_project(filename):
            backend_bridge.notify_project_saved(filename)
            return f"✅ Project saved to: {filename}"
        else:
            return f"❌ Failed to save project to: {filename}"
    
    @mcp.tool()
    def load_project(filename: str) -> str:
        """
        Load a Carla project file
        
        Args:
            filename: Path to the project file to load (.carxp)
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend bridge not available"
        
        # Check if file exists
        if not os.path.exists(filename):
            return f"❌ Project file not found: {filename}"
        
        if backend_bridge.load_project(filename):
            backend_bridge.notify_project_loaded(filename)
            return f"✅ Project loaded from: {filename}"
        else:
            return f"❌ Failed to load project from: {filename}"
    
    @mcp.tool()
    def get_current_project() -> str:
        """
        Get the filename of the currently loaded project
        
        Returns:
            Current project filename or status message
        """
        if not backend_bridge:
            return "❌ Backend bridge not available"
        
        filename = backend_bridge.get_current_project_filename()
        if filename:
            return f"📁 Current project: {filename}"
        else:
            return "📁 No project file set (unsaved session)"
    
    @mcp.tool()
    def save_plugin_state(plugin_id: int, filename: str) -> str:
        """
        Save a plugin's state to file
        
        Args:
            plugin_id: Plugin ID (0-based index)
            filename: Path where to save the state file (should end with .carxs)
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend bridge not available"
        
        # Ensure .carxs extension
        if not filename.endswith('.carxs'):
            filename += '.carxs'
        
        # Create directory if it doesn't exist
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except Exception as e:
                return f"❌ Failed to create directory: {e}"
        
        # Get plugin name for better feedback
        plugin_info = backend_bridge.get_plugin_info(plugin_id)
        plugin_name = plugin_info.get('name', f'Plugin {plugin_id}') if plugin_info else f'Plugin {plugin_id}'
        
        if backend_bridge.save_plugin_state(plugin_id, filename):
            return f"✅ Saved {plugin_name} state to: {filename}"
        else:
            return f"❌ Failed to save {plugin_name} state"
    
    @mcp.tool()
    def load_plugin_state(plugin_id: int, filename: str) -> str:
        """
        Load a plugin state from file
        
        Args:
            plugin_id: Plugin ID (0-based index)
            filename: Path to the state file (.carxs)
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend bridge not available"
        
        # Check if file exists
        if not os.path.exists(filename):
            return f"❌ State file not found: {filename}"
        
        # Get plugin name for better feedback
        plugin_info = backend_bridge.get_plugin_info(plugin_id)
        plugin_name = plugin_info.get('name', f'Plugin {plugin_id}') if plugin_info else f'Plugin {plugin_id}'
        
        if backend_bridge.load_plugin_state(plugin_id, filename):
            return f"✅ Loaded {plugin_name} state from: {filename}"
        else:
            return f"❌ Failed to load {plugin_name} state"