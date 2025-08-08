#!/usr/bin/env python3
"""
Direct test of backend_bridge.patchbay_connect function

This test bypasses all the port name resolution and group mapping logic
and calls the patchbay_connect function directly with the raw port numbers
from the connection list: Group 0 Port 510 → Group 27 Port 255
"""

import sys
import os
import logging

# Add the carla_mcp module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'source', 'frontend'))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_direct_patchbay_connect():
    """Test direct patchbay connection with raw port numbers"""
    
    try:
        # Import the MCP server and get the backend bridge
        from carla_mcp.main import CarlaBackendBridge
        
        # We need to get the actual backend bridge instance
        # This requires starting the MCP server or getting access to the host
        logger.info("This test requires the MCP server to be running to access the backend bridge")
        logger.info("Please run this test after starting the MCP server")
        
        # For now, let's show what the test would do
        logger.info("=== DIRECT PATCHBAY CONNECTION TEST ===")
        logger.info("Would call: backend_bridge.patchbay_connect(0, 510, 27, 255)")
        logger.info("This tests the raw connection from the working connection list:")
        logger.info("  Group 0 Port 510 → Group 27 Port 255")
        
        return False  # Can't actually test without running MCP server
        
    except ImportError as e:
        logger.error(f"Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error in test: {e}")
        return False

def test_with_backend_bridge(backend_bridge):
    """
    Test function that can be called with an actual backend bridge instance
    
    Args:
        backend_bridge: CarlaBackendBridge instance from the running MCP server
    """
    logger.info("=== DIRECT PATCHBAY CONNECTION TEST ===")
    logger.info("Testing direct call to backend_bridge.patchbay_connect(0, 510, 27, 255)")
    
    try:
        # Check if engine is running
        if not backend_bridge.is_engine_running():
            logger.error("Engine is not running - cannot test patchbay connection")
            return False
        
        # Check if in patchbay mode
        current_mode = backend_bridge.get_engine_process_mode()
        if current_mode != 3:  # ENGINE_PROCESS_MODE_PATCHBAY
            logger.error(f"Engine not in patchbay mode (current mode: {current_mode})")
            return False
        
        # Get current groups for reference
        groups = backend_bridge.get_patchbay_groups()
        logger.info(f"Available groups: {len(groups)}")
        for group in groups:
            logger.info(f"  Group {group['id']}: {group['name']} (type: {group.get('type', 'unknown')})")
        
        # Test the direct connection
        logger.info("Calling backend_bridge.patchbay_connect(0, 510, 27, 255)")
        
        success = backend_bridge.patchbay_connect(0, 510, 27, 255)
        
        if success:
            logger.info("✓ SUCCESS: Direct patchbay connection worked!")
            
            # Show current connections
            connections = backend_bridge.get_patchbay_connections()
            logger.info(f"Current connections: {len(connections)}")
            for conn in connections:
                logger.info(f"  Connection {conn['id']}: Group {conn['group_a']} Port {conn['port_a']} → Group {conn['group_b']} Port {conn['port_b']}")
            
            return True
        else:
            logger.error("✗ FAILED: Direct patchbay connection failed")
            
            # Get error details
            error = backend_bridge.get_last_patchbay_error()
            if error:
                logger.error(f"Error: {error}")
            
            return False
            
    except Exception as e:
        logger.error(f"Exception during test: {e}")
        return False

if __name__ == "__main__":
    # Run the basic test (which will show what we would do)
    test_direct_patchbay_connect()
    
    print("\n" + "="*60)
    print("TO RUN THE ACTUAL TEST:")
    print("1. Start the MCP server")
    print("2. In the MCP session, import this module:")
    print("   from test_direct_patchbay_connect import test_with_backend_bridge")
    print("3. Call: test_with_backend_bridge(backend_bridge)")
    print("="*60)