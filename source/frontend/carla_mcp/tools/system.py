"""
System configuration tools for Carla MCP Server

Tools for controlling engine options and system settings.
"""

from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge
from carla_backend import ENGINE_OPTION_PARALLEL_PROCESSING

# Global instances - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


def register_system_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register system configuration tools with the MCP server"""
    global backend_bridge
    backend_bridge = bridge
    
    @mcp.tool()
    def set_parallel_processing(enabled: bool) -> str:
        """
        Enable or disable parallel processing of plugins in rack mode.
        
        When enabled, plugins will be processed in parallel threads instead of sequentially.
        This can improve performance on multi-core systems, especially with CPU-heavy plugins
        like Neural Amp Modeler.
        
        Args:
            enabled: True to enable parallel processing, False to disable
            
        Returns:
            Status message indicating success or failure
            
        Note:
            - Only works in rack mode (ENGINE_PROCESS_MODE_CONTINUOUS_RACK)
            - Cannot be changed while the engine is running
            - Experimental feature - may not work with all plugin combinations
        """
        try:
            # Check if engine is running
            if backend_bridge.carla_host and backend_bridge.carla_host.is_engine_running():
                return "❌ Cannot change parallel processing while engine is running. Please close the engine first."
            
            # Set the option
            backend_bridge.carla_host.set_engine_option(
                ENGINE_OPTION_PARALLEL_PROCESSING, 
                1 if enabled else 0, 
                ""
            )
            
            status = "enabled" if enabled else "disabled"
            return f"✅ Parallel processing {status}. This will take effect when the engine starts."
            
        except Exception as e:
            return f"❌ Failed to set parallel processing: {e}"
    
    @mcp.tool()
    def get_parallel_processing_status() -> str:
        """
        Get the current parallel processing status.
        
        Returns:
            Status message indicating whether parallel processing is enabled
        """
        try:
            if not backend_bridge.carla_host:
                return "❌ Carla host not available"
            
            # Get engine options
            options = backend_bridge.carla_host.get_engine_options()
            if hasattr(options, 'parallelProcessing'):
                status = "enabled" if options.parallelProcessing else "disabled"
                return f"Parallel processing is currently {status}"
            else:
                return "❌ Parallel processing option not available in this version of Carla"
                
        except Exception as e:
            return f"❌ Failed to get parallel processing status: {e}"