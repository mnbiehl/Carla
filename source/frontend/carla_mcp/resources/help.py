"""
Help resources for Carla MCP Server

Resources providing documentation and usage information.
"""

from fastmcp import FastMCP
from ..backend.osc_client import CarlaOSCClient

# Global client instance - will be initialized in main.py
carla_client: CarlaOSCClient = None


def register_help_resources(mcp: FastMCP, client: CarlaOSCClient):
    """Register help and documentation resources with the MCP server"""
    global carla_client
    carla_client = client
    
    @mcp.resource("carla://help")
    def get_help() -> str:
        """Get help information about available Carla MCP commands"""
        help_text = """
# Carla MCP Server Help

## Available Tools:

### Connection
- `test_carla_connection()` - Test connection to Carla OSC interface

### Plugin Control
- `set_plugin_active(plugin_id, active)` - Activate/deactivate plugins
- `set_plugin_volume(plugin_id, volume)` - Set plugin volume (0.0-1.27)
- `set_plugin_parameter(plugin_id, parameter_id, value)` - Set parameter values

### MIDI Control
- `send_midi_note_on(plugin_id, channel, note, velocity)` - Send MIDI note-on
- `send_midi_note_off(plugin_id, channel, note)` - Send MIDI note-off

## Plugin IDs
Plugins are identified by their position in Carla's rack (0-based index).
The first plugin loaded is ID 0, second is ID 1, etc.

## Usage Examples:
- "Test if Carla is connected" → test_carla_connection()
- "Turn on the first plugin" → set_plugin_active(0, True)
- "Set reverb to 50% wet" → set_plugin_parameter(1, 0, 0.5)
- "Play middle C on the synth" → send_midi_note_on(0, 0, 60, 100)

## Setup Requirements:
1. Carla must be running
2. OSC must be enabled in Carla settings
3. Default OSC port is 19735 (UDP)
"""
        return help_text