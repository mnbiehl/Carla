"""
Parameter control tools for Carla MCP Server

Tools for manipulating plugin parameters and settings.
"""

import json
from typing import List, Dict, Any
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_parameter_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register parameter control tools with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    @mcp.tool()
    def set_plugin_parameter(plugin_id: int, parameter_id: int, value: float) -> str:
        """
        Set a parameter value for a plugin in Carla
        
        Args:
            plugin_id: The ID of the plugin (0-based index)
            parameter_id: The parameter ID within the plugin
            value: Parameter value (typically 0.0 to 1.0, but depends on parameter)
        """
        if not backend_bridge.is_engine_running():
            return "❌ Cannot set parameter: Carla engine is not running"
        
        if backend_bridge.set_parameter_value(plugin_id, parameter_id, value):
            return f"✅ Set plugin {plugin_id} parameter {parameter_id} to {value:.3f}"
        else:
            return f"❌ Failed to set plugin {plugin_id} parameter {parameter_id}"
    
    @mcp.tool()
    def set_plugin_parameters_batch(plugin_id: int, parameters: List[Dict[str, Any]]) -> str:
        """
        Set multiple parameters for a single plugin efficiently
        
        Args:
            plugin_id: The ID of the plugin (0-based index)
            parameters: List of parameter changes, each with "param_id" and "value" keys
                       Example: [{"param_id": 0, "value": 0.5}, {"param_id": 1, "value": 0.8}]
        
        Returns:
            JSON string with detailed results for each parameter
        """
        if not backend_bridge.is_engine_running():
            return json.dumps({
                "success": False,
                "error": "Carla engine is not running",
                "results": []
            })
        
        # Validate input format
        try:
            param_changes = []
            for i, param in enumerate(parameters):
                if not isinstance(param, dict) or "param_id" not in param or "value" not in param:
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid parameter format at index {i}. Expected dict with 'param_id' and 'value' keys",
                        "results": []
                    })
                param_changes.append((param["param_id"], param["value"]))
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error parsing parameters: {e}",
                "results": []
            })
        
        # Execute batch operation
        result = backend_bridge.set_parameters_batch(plugin_id, param_changes)
        
        # Format response for user
        if result["success"]:
            return json.dumps({
                "success": True,
                "message": f"✅ Successfully set {result['success_count']}/{result['total_count']} parameters for plugin {plugin_id}",
                "success_count": result["success_count"],
                "total_count": result["total_count"],
                "results": result["results"],
                "errors": result["errors"] if result["errors"] else None
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "message": f"❌ Failed to set parameters for plugin {plugin_id}: {result.get('error', 'Unknown error')}",
                "results": result["results"],
                "errors": result["errors"]
            }, indent=2)
    
    @mcp.tool()
    def set_multiple_plugin_parameters(changes: List[Dict[str, Any]]) -> str:
        """
        Set parameters across multiple plugins efficiently
        
        Args:
            changes: List of parameter changes across plugins
                    Each item should have "plugin_id", "param_id", and "value" keys
                    Example: [
                        {"plugin_id": 0, "param_id": 1, "value": 0.5},
                        {"plugin_id": 1, "param_id": 3, "value": 0.8},
                        {"plugin_id": 0, "param_id": 2, "value": 0.3}
                    ]
        
        Returns:
            JSON string with detailed results grouped by plugin
        """
        if not backend_bridge.is_engine_running():
            return json.dumps({
                "success": False,
                "error": "Carla engine is not running",
                "results": {}
            })
        
        # Validate input format
        try:
            for i, change in enumerate(changes):
                if not isinstance(change, dict):
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid change format at index {i}. Expected dict",
                        "results": {}
                    })
                
                required_keys = ["plugin_id", "param_id", "value"]
                for key in required_keys:
                    if key not in change:
                        return json.dumps({
                            "success": False,
                            "error": f"Missing '{key}' in change at index {i}",
                            "results": {}
                        })
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error parsing changes: {e}",
                "results": {}
            })
        
        # Execute batch operation
        result = backend_bridge.set_multiple_plugin_parameters(changes)
        
        # Format response for user
        if result["success"]:
            return json.dumps({
                "success": True,
                "message": f"✅ Successfully set {result['success_count']}/{result['total_count']} parameters across {result['plugins_affected']} plugins",
                "success_count": result["success_count"],
                "total_count": result["total_count"],
                "plugins_affected": result["plugins_affected"],
                "results": result["results"],
                "errors": result["errors"] if result["errors"] else None
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "message": f"❌ Failed to set parameters: {result.get('error', 'Unknown error')}",
                "results": result["results"],
                "errors": result["errors"]
            }, indent=2)