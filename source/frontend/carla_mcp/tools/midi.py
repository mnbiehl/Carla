"""
MIDI control tools for Carla MCP Server

Tools for sending MIDI messages and controlling MIDI functionality.
"""

from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_midi_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register MIDI control tools with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    @mcp.tool()
    def send_midi_note_on(plugin_id: int, channel: int, note: int, velocity: int) -> str:
        """
        Send a MIDI note-on message to a plugin
        
        Args:
            plugin_id: The ID of the plugin (0-based index)
            channel: MIDI channel (0-15)
            note: MIDI note number (0-127)
            velocity: Note velocity (0-127)
        """
        if not (0 <= channel <= 15):
            return "❌ MIDI channel must be between 0 and 15"
        if not (0 <= note <= 127):
            return "❌ MIDI note must be between 0 and 127"
        if not (0 <= velocity <= 127):
            return "❌ MIDI velocity must be between 0 and 127"
        
        if not backend_bridge.is_engine_running():
            return "❌ Cannot send MIDI: Carla engine is not running"
        
        if backend_bridge.send_midi_note_on(plugin_id, channel, note, velocity):
            return f"✅ Sent MIDI note-on: plugin {plugin_id}, ch {channel}, note {note}, vel {velocity}"
        else:
            return f"❌ Failed to send MIDI note-on to plugin {plugin_id}"
    
    @mcp.tool()
    def send_midi_note_off(plugin_id: int, channel: int, note: int) -> str:
        """
        Send a MIDI note-off message to a plugin
        
        Args:
            plugin_id: The ID of the plugin (0-based index)
            channel: MIDI channel (0-15)
            note: MIDI note number (0-127)
        """
        if not (0 <= channel <= 15):
            return "❌ MIDI channel must be between 0 and 15"
        if not (0 <= note <= 127):
            return "❌ MIDI note must be between 0 and 127"
        
        if backend_bridge.send_midi_note_off(plugin_id, channel, note):
            return f"✅ Sent MIDI note-off: plugin {plugin_id}, ch {channel}, note {note}"
        else:
            return f"❌ Failed to send MIDI note-off to plugin {plugin_id}"