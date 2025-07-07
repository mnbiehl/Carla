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
        if not backend_bridge or not CARLA_BACKEND_AVAILABLE:
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
        if not backend_bridge or not CARLA_BACKEND_AVAILABLE:
            return "❌ Backend API not available. Engine info requires direct backend access."
        
        try:
            engine_info = backend_bridge.get_runtime_engine_info()
            
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
        prereq_error = check_prerequisites(backend_required=True, engine_required=False)
        if prereq_error:
            return prereq_error
        
        handler = get_error_handler()
        
        def init_operation():
            success = backend_bridge.initialize_engine(driver_name, device_name)
            if success:
                engine_info = backend_bridge.get_runtime_engine_info()
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
        if not backend_bridge or not CARLA_BACKEND_AVAILABLE:
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
        if not backend_bridge or not CARLA_BACKEND_AVAILABLE:
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