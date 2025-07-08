"""
Audio routing tools for Carla MCP Server

Tools for managing audio/MIDI connections and patchbay operations.
"""

import json
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge
from ..utils.error_handler import get_error_handler

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_routing_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register audio routing tools with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    @mcp.tool()
    def get_audio_drivers() -> str:
        """
        Get list of available audio drivers
        
        Returns:
            JSON string with driver information
        """
        if not backend_bridge:
            return "❌ Backend API not available. Driver info requires direct backend access."
        
        try:
            driver_count = backend_bridge.get_engine_driver_count()
            drivers = []
            
            for i in range(driver_count):
                driver_name = backend_bridge.get_engine_driver_name(i)
                if driver_name:
                    device_names = backend_bridge.get_engine_driver_device_names(i)
                    drivers.append({
                        'index': i,
                        'name': driver_name,
                        'devices': device_names or []
                    })
            
            result = {
                'driver_count': driver_count,
                'drivers': drivers
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"❌ Error getting audio drivers: {e}"
    
    @mcp.tool()
    def get_current_engine_info() -> str:
        """
        Get information about the current engine setup
        
        Returns:
            JSON string with engine information
        """
        if not backend_bridge:
            return "❌ Backend API not available. Engine info requires direct backend access."
        
        try:
            engine_info = backend_bridge.get_engine_info()
            
            if not engine_info:
                return "❌ Engine not initialized or no info available"
            
            return json.dumps(engine_info, indent=2)
            
        except Exception as e:
            return f"❌ Error getting engine info: {e}"
    
    @mcp.tool()
    def initialize_engine(driver_name: str = "JACK", device_name: str = "") -> str:
        """
        Initialize the Carla audio engine with specified driver
        
        Args:
            driver_name: Audio driver to use (JACK, ALSA, PulseAudio, etc.)
            device_name: Specific device name (optional)
            
        Returns:
            Status message
        """
        # Check prerequisites
        if not backend_bridge:
            return "❌ Backend API not available. Engine initialization requires direct backend access."
        
        handler = get_error_handler()
        
        def init_operation():
            success = backend_bridge.initialize_engine(driver_name, device_name)
            if success:
                engine_info = backend_bridge.get_engine_info()
                if engine_info:
                    details = (f"Device: {engine_info.get('device', 'default')}\n"
                              f"Sample Rate: {engine_info.get('sample_rate', 'unknown')}\n"
                              f"Buffer Size: {engine_info.get('buffer_size', 'unknown')}")
                    return f"Engine initialized with {driver_name}\n{details}"
                else:
                    return f"Engine initialized with {driver_name}"
            return False
        
        return handler.handle_backend_operation(
            operation="initialize_engine",
            operation_func=init_operation,
            success_message="",  # Will be set by init_operation
            error_message=f"Failed to initialize engine with {driver_name}"
        )
    
    @mcp.tool()
    def close_engine() -> str:
        """
        Close the Carla audio engine
        
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available. Engine control requires direct backend access."
        
        try:
            backend_bridge.close_engine()
            return "✅ Engine closed successfully"
            
        except Exception as e:
            return f"❌ Error closing engine: {e}"
    
    @mcp.tool()
    def get_plugin_ports(plugin_id: int) -> str:
        """
        Get audio and MIDI port information for a plugin
        
        Args:
            plugin_id: ID of the plugin (0-based index)
            
        Returns:
            JSON string with port information
        """
        if not backend_bridge:
            return "❌ Backend API not available. Port info requires direct backend access."
        
        try:
            plugin_info = backend_bridge.get_plugin_info(plugin_id)
            if not plugin_info:
                return f"❌ Plugin {plugin_id} not found"
            
            # Get audio port counts
            audio_ports = {}
            midi_ports = {}
            
            try:
                audio_port_info = backend_bridge.host.get_audio_port_count_info(plugin_id)
                if audio_port_info:
                    audio_ports = {
                        'inputs': audio_port_info.ins,
                        'outputs': audio_port_info.outs
                    }
            except:
                audio_ports = {'inputs': 0, 'outputs': 0}
            
            try:
                midi_port_info = backend_bridge.host.get_midi_port_count_info(plugin_id)
                if midi_port_info:
                    midi_ports = {
                        'inputs': midi_port_info.ins,
                        'outputs': midi_port_info.outs
                    }
            except:
                midi_ports = {'inputs': 0, 'outputs': 0}
            
            result = {
                'plugin_id': plugin_id,
                'plugin_name': plugin_info.get('name', 'Unknown'),
                'audio_ports': audio_ports,
                'midi_ports': midi_ports
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"❌ Error getting port info for plugin {plugin_id}: {e}"
    
    # --------------------------------------------------------------------------------------------------------
    # Patchbay Mode and Routing Tools
    
    @mcp.tool()
    def switch_to_patchbay_mode() -> str:
        """
        Switch Carla from rack mode to patchbay mode
        
        Patchbay mode allows individual effects chains by exposing each plugin
        as a separate port group that can be freely connected.
        
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available. Mode switching requires direct backend access."
        
        try:
            # Constants from carla_backend.py
            ENGINE_PROCESS_MODE_PATCHBAY = 3
            
            current_mode = backend_bridge.get_engine_process_mode()
            if current_mode == ENGINE_PROCESS_MODE_PATCHBAY:
                return "✅ Already in patchbay mode"
            
            success = backend_bridge.set_engine_process_mode(ENGINE_PROCESS_MODE_PATCHBAY)
            if success:
                # Refresh patchbay after mode switch
                backend_bridge.patchbay_refresh()
                return "✅ Successfully switched to patchbay mode. Each plugin now has individual ports for flexible routing."
            else:
                return "❌ Failed to switch to patchbay mode. Engine may need to be restarted."
                
        except Exception as e:
            return f"❌ Error switching to patchbay mode: {e}"
    
    @mcp.tool()
    def switch_to_rack_mode() -> str:
        """
        Switch Carla back to rack mode
        
        Rack mode processes all plugins in series (Plugin1 → Plugin2 → Plugin3).
        
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available. Mode switching requires direct backend access."
        
        try:
            # Constants from carla_backend.py
            ENGINE_PROCESS_MODE_CONTINUOUS_RACK = 2
            
            current_mode = backend_bridge.get_engine_process_mode()
            if current_mode == ENGINE_PROCESS_MODE_CONTINUOUS_RACK:
                return "✅ Already in rack mode"
            
            success = backend_bridge.set_engine_process_mode(ENGINE_PROCESS_MODE_CONTINUOUS_RACK)
            if success:
                return "✅ Successfully switched to rack mode. All plugins now process in series."
            else:
                return "❌ Failed to switch to rack mode."
                
        except Exception as e:
            return f"❌ Error switching to rack mode: {e}"
    
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
    def connect_patchbay_ports(group_a_name: str, port_a_name: str, group_b_name: str, port_b_name: str) -> str:
        """
        Connect two ports in patchbay mode
        
        Args:
            group_a_name: Source port group name (e.g., "System", "Delay Plugin")
            port_a_name: Source port name (e.g., "output_1", "capture_1")
            group_b_name: Destination port group name
            port_b_name: Destination port name (e.g., "input_1", "playback_1")
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available."
        
        try:
            # Check if in patchbay mode
            current_mode = backend_bridge.get_engine_process_mode()
            if current_mode != 3:  # ENGINE_PROCESS_MODE_PATCHBAY
                return "❌ Port connections only work in patchbay mode. Use switch_to_patchbay_mode() first."
            
            # Get available groups to find IDs
            groups = backend_bridge.get_patchbay_groups()
            
            # Find group IDs by name
            group_a_id = None
            group_b_id = None
            
            for group in groups:
                if group['name'].lower() == group_a_name.lower():
                    group_a_id = group['id']
                if group['name'].lower() == group_b_name.lower():
                    group_b_id = group['id']
            
            if group_a_id is None:
                return f"❌ Source group '{group_a_name}' not found. Available groups: {[g['name'] for g in groups]}"
            
            if group_b_id is None:
                return f"❌ Destination group '{group_b_name}' not found. Available groups: {[g['name'] for g in groups]}"
            
            # Port offset constants from Carla backend
            # Audio ports need proper offsets:
            # - Audio inputs: 255 + port_index
            # - Audio outputs: 510 + port_index
            kAudioInputPortOffset = 255
            kAudioOutputPortOffset = 510
            
            # Parse port names and determine type/index
            port_a_id = 0
            port_b_id = 0
            
            # Common port naming patterns
            if any(x in port_a_name.lower() for x in ['output', 'out', 'capture']):
                # Source is output port
                if '2' in port_a_name or 'r' in port_a_name.lower():
                    port_a_id = kAudioOutputPortOffset + 1  # Right channel
                else:
                    port_a_id = kAudioOutputPortOffset + 0  # Left channel
            elif any(x in port_a_name.lower() for x in ['input', 'in']):
                # Source is input port (less common for sources)
                if '2' in port_a_name or 'r' in port_a_name.lower():
                    port_a_id = kAudioInputPortOffset + 1
                else:
                    port_a_id = kAudioInputPortOffset + 0
            
            if any(x in port_b_name.lower() for x in ['input', 'in', 'playback']):
                # Destination is input port
                if '2' in port_b_name or 'r' in port_b_name.lower():
                    port_b_id = kAudioInputPortOffset + 1  # Right channel
                else:
                    port_b_id = kAudioInputPortOffset + 0  # Left channel
            elif any(x in port_b_name.lower() for x in ['output', 'out']):
                # Destination is output port (less common for destinations)
                if '2' in port_b_name or 'r' in port_b_name.lower():
                    port_b_id = kAudioOutputPortOffset + 1
                else:
                    port_b_id = kAudioOutputPortOffset + 0
            
            success = backend_bridge.patchbay_connect(group_a_id, port_a_id, group_b_id, port_b_id)
            if success:
                return f"✅ Connected {group_a_name}:{port_a_name} → {group_b_name}:{port_b_name}"
            else:
                return f"❌ Failed to connect {group_a_name}:{port_a_name} → {group_b_name}:{port_b_name}"
                
        except Exception as e:
            return f"❌ Error connecting ports: {e}"
    
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
            
            # Note: This is a simplified implementation
            # The Carla backend doesn't expose a direct "get_connections" method
            # In a full implementation, this would need to track connections
            # or parse them from the patchbay state
            
            result = {
                'mode': 'patchbay',
                'message': 'Connection listing not yet implemented. Use Carla GUI patchbay view for now.',
                'suggestion': 'Check the Carla patchbay tab to see current connections visually.'
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"❌ Error listing connections: {e}"