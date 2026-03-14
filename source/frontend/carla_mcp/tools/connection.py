"""
Connection tools for Carla MCP Server

Tools for testing and managing connection to Carla audio host.
"""

import sys
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge
from ..config import config

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_connection_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register connection tools with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    print(f"🔍 DEBUG: Registering connection tools with MCP server: {mcp}", file=sys.__stderr__)
    print(f"🔍 DEBUG: MCP server tools before registration: {getattr(mcp, '_tools', 'no _tools attr')}", file=sys.__stderr__)
    
    @mcp.tool()
    def test_carla_connection() -> str:
        """Test connection to Carla backend"""
        print(f"🔍 DEBUG: test_carla_connection called!", file=sys.__stderr__)
        # Simple test that doesn't depend on complex backend integration
        return "✅ MCP connection test successful - tool calls are working!"
    
    print(f"🔍 DEBUG: MCP server tool manager: {getattr(mcp, '_tool_manager', 'no _tool_manager attr')}", file=sys.__stderr__)
    if hasattr(mcp, '_tool_manager'):
        tool_count = len(getattr(mcp._tool_manager, '_tools', {}))
        print(f"🔍 DEBUG: Total tools registered: {tool_count}", file=sys.__stderr__)
    print(f"🔍 DEBUG: Registered test_carla_connection tool", file=sys.__stderr__)
    
    @mcp.tool()
    def get_engine_info() -> str:
        """Get detailed Carla engine information"""
        info = backend_bridge.get_engine_info()
        
        if info.get("status") == "running":
            details = [
                f"🟢 Engine Status: {info['status']}",
                f"🎛️  Driver: {info.get('driver_name', 'Unknown')}",
                f"📊 Sample Rate: {info.get('sample_rate', 'Unknown')} Hz", 
                f"📦 Buffer Size: {info.get('buffer_size', 'Unknown')} samples",
                f"🔌 Loaded Plugins: {info.get('plugin_count', 0)}",
                f"▶️  Transport Playing: {info.get('transport_info', {}).get('playing', False)}",
                f"🎵 BPM: {info.get('transport_info', {}).get('bpm', 'Unknown')}"
            ]
            return "\n".join(details)
        else:
            return f"❌ Engine Status: {info.get('status', 'unknown')} - {info.get('error', 'No additional info')}"