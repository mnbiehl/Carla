"""
Audio routing tools for Carla MCP Server

Tools for managing audio/MIDI connections and patchbay operations.
"""

import json
from typing import List, Dict
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge
from ..utils.error_handler import get_error_handler
from ..constants import (
    PATCHBAY_PORT_AUDIO_INPUT_OFFSET,
    PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET
)

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_routing_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register audio routing tools with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    # --------------------------------------------------------------------------------------------------------
    # Patchbay Mode and Routing Tools
    
    @mcp.tool()
    def get_current_engine_mode() -> str:
        """
        Get current engine mode (rack/patchbay)
        
        Returns:
            Current engine mode description
        """
        if not backend_bridge:
            return "❌ Backend API not available."
        
        try:
            mode = backend_bridge.get_engine_process_mode()
            mode_names = {
                2: "Rack Mode (series processing)",
                3: "Patchbay Mode (flexible routing)", 
                -1: "Unknown/Error"
            }
            
            mode_name = mode_names.get(mode, f"Unknown mode ({mode})")
            return f"🎛️ Current engine mode: {mode_name}"
            
        except Exception as e:
            return f"❌ Error getting engine mode: {e}"
    
    @mcp.tool()
    def refresh_patchbay() -> str:
        """
        Refresh patchbay connections and state
        
        This is typically only needed in special circumstances like:
        - After external changes to the patchbay
        - To resync if connections appear out of sync
        
        NOT needed after:
        - Adding/removing plugins (automatic)
        - Making connections (automatic)
        - Normal patchbay operations
        
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available."
        
        try:
            success = backend_bridge.patchbay_refresh()
            if success:
                return "✅ Patchbay refreshed successfully"
            else:
                return "❌ Failed to refresh patchbay"
        except Exception as e:
            return f"❌ Error refreshing patchbay: {e}"
    
    @mcp.tool()
    def get_patchbay_groups() -> str:
        """
        List all available port groups in patchbay mode
        
        Shows system audio ports, plugin groups, and external clients like loopers.
        
        Returns:
            JSON string with group information
        """
        if not backend_bridge:
            return "❌ Backend API not available."
        
        try:
            # Check if in patchbay mode
            current_mode = backend_bridge.get_engine_process_mode()
            if current_mode != 3:  # ENGINE_PROCESS_MODE_PATCHBAY
                return "❌ Patchbay groups only available in patchbay mode. Use switch_to_patchbay_mode() first."
            
            groups = backend_bridge.get_patchbay_groups()
            
            result = {
                'mode': 'patchbay',
                'group_count': len(groups),
                'groups': groups
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"❌ Error getting patchbay groups: {e}"
    
    @mcp.tool()
    def list_patchbay_connections() -> str:
        """
        Show all current patchbay connections
        
        Returns:
            JSON string with connection information
        """
        if not backend_bridge:
            return "❌ Backend API not available."
        
        try:
            # Check if in patchbay mode
            current_mode = backend_bridge.get_engine_process_mode()
            if current_mode != 3:  # ENGINE_PROCESS_MODE_PATCHBAY
                return "❌ Patchbay connections only available in patchbay mode."
            
            # Get tracked connections
            connections = backend_bridge.get_patchbay_connections()
            
            # Get groups for name mapping
            groups = backend_bridge.get_patchbay_groups()
            group_map = {g['id']: g['name'] for g in groups}
            
            # Format connections with names
            formatted_connections = []
            for conn in connections:
                # Use the group IDs directly from backend
                src_group_id = conn['group_a']
                dst_group_id = conn['group_b']
                
                formatted_connections.append({
                    'id': conn['id'],
                    'source': {
                        'group_id': src_group_id,
                        'group_name': group_map.get(src_group_id, f"Unknown({src_group_id})"),
                        'port_id': conn['port_a']
                    },
                    'destination': {
                        'group_id': dst_group_id,
                        'group_name': group_map.get(dst_group_id, f"Unknown({dst_group_id})"),
                        'port_id': conn['port_b']
                    }
                })
            
            result = {
                'mode': 'patchbay',
                'connection_count': len(connections),
                'connections': formatted_connections
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"❌ Error listing connections: {e}"
    
    @mcp.tool()
    def disconnect_patchbay_connection(connection_id: int) -> str:
        """
        Disconnect a patchbay connection by ID
        
        Use list_patchbay_connections() to get connection IDs
        
        Args:
            connection_id: The connection ID to disconnect
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available."
        
        try:
            # Check if in patchbay mode
            current_mode = backend_bridge.get_engine_process_mode()
            if current_mode != 3:  # ENGINE_PROCESS_MODE_PATCHBAY
                return "❌ Port disconnection only works in patchbay mode."
            
            # Disconnect using the connection ID
            success = backend_bridge.patchbay_disconnect(connection_id)
            
            if success:
                return f"✅ Disconnected connection ID {connection_id}"
            else:
                return f"❌ Failed to disconnect connection ID {connection_id}"
            
        except Exception as e:
            return f"❌ Error disconnecting connection: {e}"
    

    @mcp.tool()
    def connect_plugins(source_plugin_id: int, dest_plugin_id: int, 
                       source_channel: str = "stereo", dest_channel: str = "stereo") -> str:
        """
        Connect audio output of one plugin to input of another
        
        This is a simplified high-level API that handles all the complex
        group ID and port offset calculations internally.
        
        Args:
            source_plugin_id: Source plugin ID (0-based)
            dest_plugin_id: Destination plugin ID (0-based)
            source_channel: "mono", "left", "right", or "stereo" (default)
            dest_channel: "mono", "left", "right", or "stereo" (default)
            
        Returns:
            Status message
            
        Examples:
            connect_plugins(0, 1)  # Connect plugin 0 output to plugin 1 input (stereo)
            connect_plugins(0, 1, "mono", "stereo")  # Mono to stereo connection
        """
        if not backend_bridge:
            return "❌ Backend API not available."
        
        try:
            # Get backend group IDs for both plugins
            source_group = backend_bridge._plugin_to_group_map.get(source_plugin_id)
            dest_group = backend_bridge._plugin_to_group_map.get(dest_plugin_id)
            
            if source_group is None:
                return f"❌ Plugin {source_plugin_id} not found in patchbay (try refresh_patchbay)"
            if dest_group is None:
                return f"❌ Plugin {dest_plugin_id} not found in patchbay (try refresh_patchbay)"
            
            # Determine port connections based on channel configuration
            connections = []
            
            if source_channel == "stereo" and dest_channel == "stereo":
                # Stereo to stereo: connect L->L and R->R
                connections.append((
                    source_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,  # Left out
                    dest_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0      # Left in
                ))
                connections.append((
                    source_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,  # Right out
                    dest_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1      # Right in
                ))
            elif source_channel == "mono":
                # Mono source: duplicate to both channels if dest is stereo
                if dest_channel == "stereo":
                    connections.append((
                        source_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                        dest_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0
                    ))
                    connections.append((
                        source_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,  # Same source
                        dest_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1
                    ))
                else:
                    # Mono to mono
                    connections.append((
                        source_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                        dest_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0
                    ))
            
            # Execute connections
            success_count = 0
            for src_group, src_port, dst_group, dst_port in connections:
                if backend_bridge.patchbay_connect(src_group, src_port, dst_group, dst_port):
                    success_count += 1
            
            if success_count == len(connections):
                plugin_names = [
                    backend_bridge.get_plugin_info(source_plugin_id).get('name', f'Plugin {source_plugin_id}'),
                    backend_bridge.get_plugin_info(dest_plugin_id).get('name', f'Plugin {dest_plugin_id}')
                ]
                return f"✅ Connected {plugin_names[0]} → {plugin_names[1]} ({source_channel} to {dest_channel})"
            else:
                return f"⚠️ Partially connected: {success_count}/{len(connections)} connections made"
                
        except Exception as e:
            return f"❌ Error connecting plugins: {e}"

    @mcp.tool()
    def connect_system_to_plugin(system_input: int, plugin_id: int, channel: str = "mono") -> str:
        """
        Connect system audio input to a plugin
        
        Args:
            system_input: System input number (1-16)
            plugin_id: Destination plugin ID
            channel: "mono", "left", "right", or "stereo"
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available."
            
        try:
            # Get plugin's backend group ID
            plugin_group = backend_bridge._plugin_to_group_map.get(plugin_id)
            if plugin_group is None:
                return f"❌ Plugin {plugin_id} not found in patchbay"
            
            # System audio input is group 1 in Carla's patchbay
            system_group = 1
            system_port = PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + (system_input - 1)
            
            connections = []
            if channel == "stereo":
                # Connect to both inputs
                connections.append((system_group, system_port,
                                  plugin_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0))
                connections.append((system_group, system_port,
                                  plugin_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1))
            elif channel == "left":
                # Connect to left input only
                connections.append((system_group, system_port,
                                  plugin_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0))
            elif channel == "right":
                # Connect to right input only
                connections.append((system_group, system_port,
                                  plugin_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 1))
            else:
                # Mono connection (same as left)
                connections.append((system_group, system_port,
                                  plugin_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + 0))
            
            # Execute connections
            success_count = 0
            for src_group, src_port, dst_group, dst_port in connections:
                if backend_bridge.patchbay_connect(src_group, src_port, dst_group, dst_port):
                    success_count += 1
            
            if success_count == len(connections):
                plugin_name = backend_bridge.get_plugin_info(plugin_id).get('name', f'Plugin {plugin_id}')
                return f"✅ Connected System Input {system_input} → {plugin_name} ({channel})"
            else:
                return f"⚠️ Partially connected: {success_count}/{len(connections)} connections made"
                
        except Exception as e:
            return f"❌ Error connecting system to plugin: {e}"

    @mcp.tool()  
    def connect_plugin_to_system(plugin_id: int, system_output_left: int, 
                                system_output_right: int = None) -> str:
        """
        Connect plugin output to system audio outputs
        
        Args:
            plugin_id: Source plugin ID
            system_output_left: System output for left channel (1-16)
            system_output_right: System output for right channel (defaults to left+1)
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available."
        
        if system_output_right is None:
            system_output_right = system_output_left + 1
            
        try:
            # Get plugin's backend group ID
            plugin_group = backend_bridge._plugin_to_group_map.get(plugin_id)
            if plugin_group is None:
                return f"❌ Plugin {plugin_id} not found in patchbay"
            
            # System audio output is group 2 in Carla's patchbay
            system_group = 2
            
            # Connect L and R channels
            connections = [
                (plugin_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 0,
                 system_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + (system_output_left - 1)),
                (plugin_group, PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + 1,
                 system_group, PATCHBAY_PORT_AUDIO_INPUT_OFFSET + (system_output_right - 1))
            ]
            
            # Execute connections
            success_count = 0
            for src_group, src_port, dst_group, dst_port in connections:
                if backend_bridge.patchbay_connect(src_group, src_port, dst_group, dst_port):
                    success_count += 1
            
            if success_count == len(connections):
                plugin_name = backend_bridge.get_plugin_info(plugin_id).get('name', f'Plugin {plugin_id}')
                return f"✅ Connected {plugin_name} → System Output {system_output_left}/{system_output_right}"
            else:
                return f"⚠️ Partially connected: {success_count}/{len(connections)} connections made"
                
        except Exception as e:
            return f"❌ Error connecting plugin to system: {e}"

    @mcp.tool()
    def debug_patchbay_groups() -> str:
        """
        Show detailed patchbay group mapping for debugging
        
        Returns:
            Detailed group and plugin mapping information
        """
        if not backend_bridge:
            return "❌ Backend API not available."
            
        info = []
        info.append("=== Patchbay Group Mapping ===")
        info.append(f"Plugin -> Group: {backend_bridge._plugin_to_group_map}")
        info.append(f"Group -> Plugin: {backend_bridge._group_to_plugin_map}")
        
        # Also show current groups
        groups = backend_bridge.get_patchbay_groups()
        info.append("\n=== Current Groups ===")
        for group in groups:
            info.append(f"Group {group['id']}: {group['name']} (type: {group.get('type')})")
            if group.get('plugin_id') is not None:
                info.append(f"  -> Plugin ID: {group['plugin_id']}")
        
        # Show current connections
        connections = backend_bridge.get_patchbay_connections()
        info.append(f"\n=== Current Connections ({len(connections)}) ===")
        for conn in connections:
            info.append(f"Connection {conn['id']}: Group {conn['group_a']} Port {conn['port_a']} → Group {conn['group_b']} Port {conn['port_b']}")
        
        return "\n".join(info)