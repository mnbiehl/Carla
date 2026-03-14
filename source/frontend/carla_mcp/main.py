#!/usr/bin/env python3
"""
Carla MCP Server - Integrated Frontend Module

A comprehensive Model Context Protocol server that provides AI control over 
Carla audio plugin host via direct backend API integration.

This module is designed to run as part of the Carla frontend, providing
MCP server functionality directly integrated with the GUI.
"""

import threading
import time
from typing import Optional
from fastmcp import FastMCP

from .config import config
from .utils.signal_handler import setup_signal_handlers, shutdown_gracefully
from .utils.logging import setup_logging
from .utils.error_handler import init_error_handler

# Global instances
mcp_server = None
mcp_thread = None
logger = None
backend_bridge = None

# Import tool registration functions
from .tools.connection import register_connection_tools
from .tools.plugins import register_plugin_tools
from .tools.parameters import register_parameter_tools
from .tools.midi import register_midi_tools
from .tools.transport import register_transport_tools
from .tools.sessions import register_session_tools
from .tools.routing import register_routing_tools
from .tools.auto_gain import register_auto_gain_tools
from .tools.system import register_system_tools

# Import resource registration functions
from .resources.status import register_status_resources
from .resources.help import register_help_resources
from .resources.monitoring import register_monitoring_resources
from .resources.realtime_monitoring import register_realtime_monitoring


def initialize_mcp_server(carla_host_instance=None):
    """Initialize the simplest possible MCP server"""
    global mcp_server, logger
    
    # Set up logging
    logger = setup_logging(config.log_level)
    
    # Create MCP server instance - minimal setup
    mcp_server = FastMCP("Carla MCP Server")
    
    logger.info("Initialized minimal MCP server")
    return mcp_server


def register_test_tool():
    """Register test tool after server is ready"""
    global mcp_server, logger
    
    # Add one simple test tool directly
    @mcp_server.tool()
    def hello_world() -> str:
        """A simple hello world test tool"""
        logger.info("hello_world tool called!")
        return "Hello from MCP server!"
    
    logger.info("Registered test tool with MCP server")


def register_custom_endpoints():
    """Register custom endpoints for Claude Code compatibility"""
    global mcp_server, logger
    
    # Add registration endpoint for dynamic client registration
    @mcp_server.custom_route("/register", methods=["POST"])
    async def register_client(request):
        """Handle dynamic client registration"""
        try:
            import json
            import uuid
            from starlette.responses import JSONResponse
            
            # Parse request body
            body = await request.json()
            client_name = body.get("client_name", "unknown")
            redirect_uris = body.get("redirect_uris", [])
            
            # Generate client ID
            client_id = str(uuid.uuid4())
            
            logger.info(f"Registering client: {client_name} with ID: {client_id}")
            
            # Return registration response
            response = {
                "client_id": client_id,
                "token_endpoint_auth_method": "none",
                "redirect_uris": redirect_uris
            }
            
            return JSONResponse(content=response, status_code=201)
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            from starlette.responses import JSONResponse
            return JSONResponse(content={"error": "Invalid request"}, status_code=400)
    
    # Add SSE endpoint for real-time monitoring
    try:
        from .resources.realtime_monitoring import create_sse_endpoint
        monitoring_endpoint = create_sse_endpoint(mcp_server)
        mcp_server.custom_route("/monitoring/events", methods=["GET"])(monitoring_endpoint)
        logger.info("Registered SSE monitoring endpoint at /monitoring/events")
    except Exception as e:
        logger.warning(f"Could not register SSE monitoring endpoint: {e}")
    
    logger.info("Registered custom endpoints for Claude Code compatibility")


def register_all_tools(backend_bridge):
    """Register all MCP tools with the server"""
    logger.info("Registering MCP tools...")

    # Register connection tools with backend bridge
    register_connection_tools(mcp_server, backend_bridge)

    # Register plugin management tools with backend bridge
    register_plugin_tools(mcp_server, backend_bridge)
    
    # Register parameter control tools
    register_parameter_tools(mcp_server, backend_bridge)
    
    # Register MIDI tools
    register_midi_tools(mcp_server, backend_bridge)
    
    # Register transport tools
    register_transport_tools(mcp_server, backend_bridge)
    
    # Register session tools
    register_session_tools(mcp_server, backend_bridge)
    
    # Register routing tools with backend support
    register_routing_tools(mcp_server, backend_bridge)
    
    # Register auto-gain tools
    register_auto_gain_tools(mcp_server, backend_bridge)
    
    # Register system configuration tools
    register_system_tools(mcp_server, backend_bridge)
    
    logger.info("All tools registered successfully")


def register_all_resources(backend_bridge):
    """Register all MCP resources with the server"""
    logger.info("Registering MCP resources...")
    
    # Register status resources
    register_status_resources(mcp_server, backend_bridge)
    
    # Register help resources
    register_help_resources(mcp_server, backend_bridge)
    
    # Register monitoring resources
    register_monitoring_resources(mcp_server, backend_bridge)
    
    # Register real-time monitoring resources
    register_realtime_monitoring(mcp_server, backend_bridge)
    
    logger.info("All resources registered successfully")


def setup_patchbay_callbacks(carla_host_instance):
    """Set up callbacks to track patchbay connections"""
    logger.info("Setting up patchbay connection tracking callbacks...")
    
    try:
        # Connect to the connection added callback
        def on_connection_added(connection_id, group_out_id, port_out_id, group_in_id, port_in_id):
            logger.info(f"Patchbay connection added: ID={connection_id}, {group_out_id}:{port_out_id} -> {group_in_id}:{port_in_id}")
            if backend_bridge:
                backend_bridge.register_connection(connection_id, group_out_id, port_out_id, group_in_id, port_in_id)
        
        # Connect to the connection removed callback
        def on_connection_removed(connection_id, port_out_id, port_in_id):
            logger.info(f"Patchbay connection removed: ID={connection_id}")
            if backend_bridge:
                backend_bridge.unregister_connection(connection_id)
        
        def on_patchbay_client_added(client_id, client_icon, plugin_id, client_name):
            logger.info(f"Patchbay client added: ID={client_id}, Plugin={plugin_id}, Name={client_name}")
            if backend_bridge:
                backend_bridge.register_patchbay_client(client_id, client_icon, plugin_id, client_name)
        
        # Connect the callbacks
        if hasattr(carla_host_instance, 'PatchbayConnectionAddedCallback'):
            carla_host_instance.PatchbayConnectionAddedCallback.connect(on_connection_added)
            logger.info("Connected to PatchbayConnectionAddedCallback")
        else:
            logger.warning("PatchbayConnectionAddedCallback not found on host instance")
            
        if hasattr(carla_host_instance, 'PatchbayConnectionRemovedCallback'):
            carla_host_instance.PatchbayConnectionRemovedCallback.connect(on_connection_removed)
            logger.info("Connected to PatchbayConnectionRemovedCallback")
        else:
            logger.warning("PatchbayConnectionRemovedCallback not found on host instance")
            
        if hasattr(carla_host_instance, 'PatchbayClientAddedCallback'):
            carla_host_instance.PatchbayClientAddedCallback.connect(on_patchbay_client_added)
            logger.info("Connected to PatchbayClientAddedCallback")
        else:
            logger.warning("PatchbayClientAddedCallback not found on host instance")
            
    except Exception as e:
        logger.error(f"Failed to set up patchbay callbacks: {e}")



def mcp_server_async_thread(carla_host_instance=None):
    """Run async MCP server in background thread"""
    global mcp_server, logger
    import asyncio
    import sys
    
    async def run_async():
        try:
            # Temporarily restore stdout/stderr for server
            carla_stdout = sys.stdout
            carla_stderr = sys.stderr
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            
            try:
                logger.info(f"Starting async MCP server with SSE transport on {config.mcp_host}:{config.mcp_port}...")
                
                # Tools and resources are already registered - use SSE-specific async runner
                await mcp_server.run_sse_async(host="127.0.0.1", port=3001)
            finally:
                sys.stdout = carla_stdout
                sys.stderr = carla_stderr
                
        except Exception as e:
            logger.error(f"Async MCP server error: {e}")
    
    # Run the async server
    asyncio.run(run_async())


def start_mcp_server(carla_host_instance=None, gui_instance=None):
    """Start the MCP server following standard FastMCP pattern"""
    global mcp_thread, logger
    
    # Validate configuration
    if not config.validate():
        if logger:
            logger.error("Invalid MCP configuration")
        return False
    
    # Initialize minimal MCP server
    initialize_mcp_server(carla_host_instance)
    
    # Register ALL tools and resources BEFORE starting server
    logger.info("Registering MCP tools and resources...")
    try:
        # Validate host instance
        if carla_host_instance is None:
            logger.error("No Carla host instance provided")
            return False
        
        # Create single backend bridge for all tools and resources
        from .backend.backend_bridge import CarlaBackendBridge
        global backend_bridge
        backend_bridge = CarlaBackendBridge(carla_host_instance)
        if gui_instance is not None:
            backend_bridge.set_gui_instance(gui_instance)
        logger.info(f"Created backend bridge: {backend_bridge}")

        # Set up callbacks to track patchbay connections
        setup_patchbay_callbacks(carla_host_instance)
        
        # Register tools and resources with shared bridge
        register_all_tools(backend_bridge)
        register_all_resources(backend_bridge)
        
        # Register custom endpoints including SSE monitoring
        register_custom_endpoints()
        
        logger.info("All tools and resources registered successfully")
    except Exception as e:
        logger.error(f"Failed to register tools and resources: {e}")
        return False
    
    # Run async server in background thread with fully configured server
    logger.info("Starting MCP server in background thread...")
    mcp_thread = threading.Thread(
        target=mcp_server_async_thread,
        args=(carla_host_instance,),
        daemon=True,
        name="MCP-AsyncServer"
    )
    mcp_thread.start()
    
    logger.info("MCP server started successfully")
    return True


def stop_mcp_server():
    """Stop the MCP server"""
    global mcp_server, mcp_thread, backend_bridge, logger
    
    if mcp_server:
        logger.info("Stopping MCP server...")
        try:
            # Mark server as stopping
            mcp_server._stopping = True
            
            # Clean up backend bridge first
            if backend_bridge:
                logger.info("Cleaning up backend bridge...")
                backend_bridge.cleanup()
            
            # Wait for server thread to finish (with timeout)
            if mcp_thread and mcp_thread.is_alive():
                logger.info("Waiting for MCP server thread to finish...")
                mcp_thread.join(timeout=5.0)  # 5 second timeout
                if mcp_thread.is_alive():
                    logger.warning("MCP server thread did not finish within timeout")
            
            # Graceful shutdown without forcing exit
            shutdown_gracefully()
            logger.info("MCP server stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping MCP server: {e}")
    
    mcp_server = None
    mcp_thread = None
    backend_bridge = None


def is_mcp_server_running():
    """Check if MCP server is running"""
    return mcp_server is not None


# Standalone mode for testing
def main():
    """Main entry point for standalone testing"""
    global logger
    
    # Set up logging
    logger = setup_logging(config.log_level)
    
    print("🎵 Starting Carla MCP Server (standalone mode)...")
    logger.info("Starting MCP server in standalone mode")
    
    # Start MCP server
    if start_mcp_server():
        print("🚀 MCP Server ready for connections")
        print("💡 Press Ctrl+C to stop the server")
        
        try:
            # Keep main thread alive
            while is_mcp_server_running():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n⏹️  Stopping MCP server...")
            stop_mcp_server()
    else:
        print("❌ Failed to start MCP server")


if __name__ == "__main__":
    main()