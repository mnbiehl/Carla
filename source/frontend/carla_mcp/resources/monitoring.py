"""
Monitoring resources for Carla MCP Server

Resources for real-time monitoring of audio levels, performance, and transport.
"""

from typing import Dict, List, Any
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_monitoring_resources(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register real-time monitoring resources with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    @mcp.resource("monitoring://audio_levels")
    def get_audio_levels() -> Dict[str, Any]:
        """
        Get current audio peak levels for all active plugins
        
        Returns a dictionary with peak values for each plugin's inputs and outputs.
        Values are in dB where 0dB = 1.0, -inf = 0.0
        
        Example response:
        {
            "plugins": [
                {
                    "id": 0,
                    "name": "TAP Reverberator",
                    "input": {"left": -12.5, "right": -13.2},
                    "output": {"left": -10.1, "right": -10.8}
                }
            ]
        }
        """
        if not backend_bridge or not backend_bridge.is_engine_running():
            return {"error": "Engine not running", "plugins": []}
        
        try:
            plugin_count = backend_bridge.host.get_current_plugin_count()
            plugins_data = []
            
            for plugin_id in range(plugin_count):
                try:
                    # Get plugin info
                    plugin_info = backend_bridge.host.get_plugin_info(plugin_id)
                    plugin_name = plugin_info['name'] if plugin_info else f"Plugin {plugin_id}"
                    
                    # Get peak values
                    input_left = backend_bridge.get_input_peak_value(plugin_id, True)
                    input_right = backend_bridge.get_input_peak_value(plugin_id, False)
                    output_left = backend_bridge.get_output_peak_value(plugin_id, True)
                    output_right = backend_bridge.get_output_peak_value(plugin_id, False)
                    
                    # Convert to dB (20 * log10(value))
                    # Handle zero values to avoid log(0)
                    def to_db(value):
                        if value <= 0:
                            return -96.0  # Effectively -inf
                        import math
                        return 20 * math.log10(value)
                    
                    plugins_data.append({
                        "id": plugin_id,
                        "name": plugin_name,
                        "input": {
                            "left": round(to_db(input_left), 1),
                            "right": round(to_db(input_right), 1),
                            "left_linear": round(input_left, 4),
                            "right_linear": round(input_right, 4)
                        },
                        "output": {
                            "left": round(to_db(output_left), 1),
                            "right": round(to_db(output_right), 1),
                            "left_linear": round(output_left, 4),
                            "right_linear": round(output_right, 4)
                        }
                    })
                except Exception as e:
                    # Log error but continue with other plugins
                    plugins_data.append({
                        "id": plugin_id,
                        "error": str(e)
                    })
            
            return {
                "plugin_count": plugin_count,
                "plugins": plugins_data
            }
            
        except Exception as e:
            return {"error": f"Failed to get audio levels: {str(e)}", "plugins": []}
    
    # Commented out - FastMCP doesn't support URI parameters in resource decorators
    # Users should use the monitoring://audio_levels resource to get all plugin levels
    # The audio_levels resource provides the same information for all plugins at once