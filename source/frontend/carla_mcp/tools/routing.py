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
        debug_info = []
        
        if not backend_bridge:
            return "❌ Backend API not available."
        
        try:
            # Check if in patchbay mode
            current_mode = backend_bridge.get_engine_process_mode()
            debug_info.append(f"Current engine mode: {current_mode}")
            if current_mode != 3:  # ENGINE_PROCESS_MODE_PATCHBAY
                return "❌ Port connections only work in patchbay mode. Use switch_to_patchbay_mode() first."
            
            # Get available groups to find IDs
            groups = backend_bridge.get_patchbay_groups()
            debug_info.append(f"Found {len(groups)} groups")
            
            # Find group IDs by name
            group_a_id = None
            group_b_id = None
            
            for group in groups:
                debug_info.append(f"Group {group['id']}: '{group['name']}' (type: {group.get('type', 'unknown')})")
                if group['name'].lower() == group_a_name.lower():
                    group_a_id = group['id']
                if group['name'].lower() == group_b_name.lower():
                    group_b_id = group['id']
            
            if group_a_id is None:
                return f"❌ Source group '{group_a_name}' not found. Available groups: {[g['name'] for g in groups]}\n\nDebug:\n" + "\n".join(debug_info)
            
            if group_b_id is None:
                return f"❌ Destination group '{group_b_name}' not found. Available groups: {[g['name'] for g in groups]}\n\nDebug:\n" + "\n".join(debug_info)
            
            # Port offset constants from Carla backend
            # Audio ports need proper offsets:
            # - Audio inputs: 255 + port_index
            # - Audio outputs: 510 + port_index
            
            # Parse port names and determine type/index
            port_a_id = 0
            port_b_id = 0
            
            # Extract port number from names like "Audio Input 1", "Capture 1", "Playback 1"
            import re
            
            # Helper function to extract port number
            def extract_port_number(port_name):
                match = re.search(r'(\d+)', port_name)
                if match:
                    return int(match.group(1)) - 1  # Convert to 0-based index
                return 0
            
            # Get source group info to determine port type
            source_group = next((g for g in groups if g['id'] == group_a_id), None)
            dest_group = next((g for g in groups if g['id'] == group_b_id), None)
            
            debug_info.append(f"\nSource group: {source_group}")
            debug_info.append(f"Dest group: {dest_group}")
            
            if source_group:
                port_index = extract_port_number(port_a_name)
                debug_info.append(f"Source port '{port_a_name}' extracted index: {port_index}")
                
                # Apply correct port offsets based on manual connection analysis
                if source_group['type'] == 'audio_input':
                    # Audio Input ports are outputs - use 510 offset
                    port_a_id = PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + port_index
                    debug_info.append(f"Source is audio_input, using OUTPUT offset: {PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET} + {port_index} = {port_a_id}")
                elif source_group['type'] == 'plugin':
                    # Plugin ports - check if it's input or output
                    if any(x in port_a_name.lower() for x in ['output', 'out']):
                        port_a_id = PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + port_index
                        debug_info.append(f"Source is plugin output, using OUTPUT offset: {PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET} + {port_index} = {port_a_id}")
                    else:
                        port_a_id = PATCHBAY_PORT_AUDIO_INPUT_OFFSET + port_index
                        debug_info.append(f"Source is plugin input, using INPUT offset: {PATCHBAY_PORT_AUDIO_INPUT_OFFSET} + {port_index} = {port_a_id}")
                else:
                    port_a_id = port_index
                    debug_info.append(f"Source using raw port index: {port_index}")
            
            if dest_group:
                port_index = extract_port_number(port_b_name)
                debug_info.append(f"Dest port '{port_b_name}' extracted index: {port_index}")
                
                # Apply correct port offsets based on manual connection analysis
                if dest_group['type'] == 'audio_output':
                    # Audio Output ports are inputs - use 255 offset
                    port_b_id = PATCHBAY_PORT_AUDIO_INPUT_OFFSET + port_index
                    debug_info.append(f"Dest is audio_output, using INPUT offset: {PATCHBAY_PORT_AUDIO_INPUT_OFFSET} + {port_index} = {port_b_id}")
                elif dest_group['type'] == 'plugin':
                    # Plugin ports - check if it's input or output
                    if any(x in port_b_name.lower() for x in ['input', 'in']):
                        port_b_id = PATCHBAY_PORT_AUDIO_INPUT_OFFSET + port_index
                        debug_info.append(f"Dest is plugin input, using INPUT offset: {PATCHBAY_PORT_AUDIO_INPUT_OFFSET} + {port_index} = {port_b_id}")
                    else:
                        port_b_id = PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + port_index
                        debug_info.append(f"Dest is plugin output, using OUTPUT offset: {PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET} + {port_index} = {port_b_id}")
                else:
                    port_b_id = port_index
                    debug_info.append(f"Dest using raw port index: {port_index}")
            
            debug_info.append(f"\nFinal connection: Group {group_a_id} Port {port_a_id} → Group {group_b_id} Port {port_b_id}")
            
            # IMPORTANT: The backend seems to use 1-based group IDs internally!
            # Add 1 to group IDs to match what the GUI uses
            # TEMPORARILY DISABLED - testing if this is causing connection failures
            # backend_group_a_id = group_a_id + 1
            # backend_group_b_id = group_b_id + 1
            backend_group_a_id = group_a_id
            backend_group_b_id = group_b_id
            
            debug_info.append(f"Adjusted for backend: Group {backend_group_a_id} Port {port_a_id} → Group {backend_group_b_id} Port {port_b_id}")
            
            success = backend_bridge.patchbay_connect(backend_group_a_id, port_a_id, backend_group_b_id, port_b_id)
            if success:
                return f"✅ Connected {group_a_name}:{port_a_name} → {group_b_name}:{port_b_name}\n\nDebug:\n" + "\n".join(debug_info)
            else:
                # Get the actual Carla error message
                carla_error = backend_bridge.get_last_patchbay_error()
                error_msg = f"❌ Failed to connect {group_a_name}:{port_a_name} → {group_b_name}:{port_b_name}"
                if carla_error:
                    error_msg += f"\n\nCarla Error: {carla_error}"
                error_msg += f"\n\nDebug:\n" + "\n".join(debug_info)
                return error_msg
                
        except Exception as e:
            return f"❌ Error connecting ports: {e}\n\nDebug:\n" + "\n".join(debug_info)
    
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
                # Adjust group IDs (subtract 1 to get back to our IDs)
                src_group_id = conn['group_a'] - 1
                dst_group_id = conn['group_b'] - 1
                
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
    def connect_patchbay_ports_batch(connections: List[Dict[str, str]]) -> str:
        """
        Connect multiple patchbay ports efficiently
        
        Args:
            connections: List of connection dictionaries, each with:
                        "group_a_name", "port_a_name", "group_b_name", "port_b_name"
                        Example: [
                            {
                                "group_a_name": "Audio Input",
                                "port_a_name": "Capture 2", 
                                "group_b_name": "C* Noisegate - Attenuate noise resident in silence",
                                "port_b_name": "Audio Input 1"
                            },
                            {
                                "group_a_name": "C* Noisegate - Attenuate noise resident in silence",
                                "port_a_name": "Audio Output 1",
                                "group_b_name": "x42-comp - Dynamic Compressor Stereo", 
                                "port_b_name": "Audio Input 1"
                            }
                        ]
        
        Returns:
            JSON string with detailed results for each connection
        """
        if not backend_bridge:
            return json.dumps({
                "success": False,
                "error": "Backend API not available",
                "results": []
            })
        
        # Check if in patchbay mode
        try:
            current_mode = backend_bridge.get_engine_process_mode()
            if current_mode != 3:  # ENGINE_PROCESS_MODE_PATCHBAY
                return json.dumps({
                    "success": False,
                    "error": "Port connections only work in patchbay mode. Use switch_to_patchbay_mode() first.",
                    "results": []
                })
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to check engine mode: {e}",
                "results": []
            })
        
        # Validate input format
        try:
            for i, conn in enumerate(connections):
                if not isinstance(conn, dict):
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid connection format at index {i}. Expected dict",
                        "results": []
                    })
                
                required_keys = ["group_a_name", "port_a_name", "group_b_name", "port_b_name"]
                for key in required_keys:
                    if key not in conn:
                        return json.dumps({
                            "success": False,
                            "error": f"Missing '{key}' in connection at index {i}",
                            "results": []
                        })
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error parsing connections: {e}",
                "results": []
            })
        
        # Get groups once for all connections (optimization)
        try:
            groups = backend_bridge.get_patchbay_groups()
            group_map = {g['name'].lower(): g for g in groups}
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to get patchbay groups: {e}",
                "results": []
            })
        
        # Execute batch connections
        results = []
        success_count = 0
        errors = []
        
        for i, conn in enumerate(connections):
            result = {
                "index": i,
                "connection": conn,
                "success": False,
                "error": None
            }
            
            try:
                # This reuses the existing single connection logic but without debug output
                group_a_name = conn["group_a_name"]
                port_a_name = conn["port_a_name"] 
                group_b_name = conn["group_b_name"]
                port_b_name = conn["port_b_name"]
                
                # Find groups
                group_a = group_map.get(group_a_name.lower())
                group_b = group_map.get(group_b_name.lower())
                
                if not group_a:
                    result["error"] = f"Source group '{group_a_name}' not found"
                elif not group_b:
                    result["error"] = f"Destination group '{group_b_name}' not found"
                else:
                    # Calculate port IDs (reusing existing logic)
                    import re
                    def extract_port_number(port_name):
                        match = re.search(r'(\d+)', port_name)
                        return int(match.group(1)) - 1 if match else 0
                    
                    # Source port calculation
                    port_index = extract_port_number(port_a_name)
                    if group_a['type'] == 'audio_input':
                        port_a_id = PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + port_index
                    elif group_a['type'] == 'plugin':
                        if any(x in port_a_name.lower() for x in ['output', 'out']):
                            port_a_id = PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + port_index
                        else:
                            port_a_id = PATCHBAY_PORT_AUDIO_INPUT_OFFSET + port_index
                    else:
                        port_a_id = PATCHBAY_PORT_AUDIO_INPUT_OFFSET + port_index
                    
                    # Destination port calculation  
                    port_index = extract_port_number(port_b_name)
                    if group_b['type'] == 'audio_output':
                        port_b_id = PATCHBAY_PORT_AUDIO_INPUT_OFFSET + port_index
                    elif group_b['type'] == 'plugin':
                        if any(x in port_b_name.lower() for x in ['input', 'in']):
                            port_b_id = PATCHBAY_PORT_AUDIO_INPUT_OFFSET + port_index
                        else:
                            port_b_id = PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + port_index
                    else:
                        port_b_id = PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET + port_index
                    
                    # Connect with backend-adjusted group IDs
                    backend_group_a_id = group_a['id'] + 1
                    backend_group_b_id = group_b['id'] + 1
                    
                    success = backend_bridge.patchbay_connect(
                        backend_group_a_id, port_a_id, 
                        backend_group_b_id, port_b_id
                    )
                    
                    if success:
                        result["success"] = True
                        success_count += 1
                    else:
                        # Get the actual Carla error message
                        carla_error = backend_bridge.get_last_patchbay_error()
                        if carla_error:
                            result["error"] = f"Patchbay connect failed: {carla_error}"
                        else:
                            result["error"] = "Patchbay connect failed"
                        
            except Exception as e:
                result["error"] = f"Exception during connection: {e}"
                
            if result["error"]:
                errors.append(result["error"])
            
            results.append(result)
        
        # Format response
        if success_count > 0:
            return json.dumps({
                "success": True,
                "message": f"✅ Successfully connected {success_count}/{len(connections)} patchbay connections",
                "success_count": success_count,
                "total_count": len(connections),
                "results": results,
                "errors": errors if errors else None
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "message": f"❌ Failed to connect any of {len(connections)} patchbay connections",
                "results": results,
                "errors": errors
            }, indent=2)