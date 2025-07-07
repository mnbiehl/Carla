"""
Signal handling utilities for Carla MCP Server

Provides clean shutdown handling for the MCP server.
"""

import logging
import signal
import sys
import os

logger = logging.getLogger(__name__)

# Global shutdown flag
_shutdown_initiated = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global _shutdown_initiated
    if not _shutdown_initiated:
        _shutdown_initiated = True
        logger.info(f"Received signal {signum}, shutting down...")
        try:
            print("\n🛑 Shutting down Carla MCP Server...")
        except (ValueError, OSError):
            pass  # Handle closed stdio
    # Let the signal propagate to terminate the process
    raise KeyboardInterrupt()


def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def shutdown_gracefully():
    """Perform graceful shutdown sequence"""
    global _shutdown_initiated
    if not _shutdown_initiated:
        _shutdown_initiated = True
        try:
            print("\n🛑 Shutting down Carla MCP Server...")
        except (ValueError, OSError):
            pass  # Handle closed stdio
    
    logger.info("Server shutdown complete")
    # Force immediate exit to avoid stdio issues
    try:
        print("👋 Goodbye!")
        sys.stdout.flush()
    except (ValueError, OSError):
        pass
    os._exit(0)


# Expose shutdown event for external modules
def shutdown_event():
    """Check if shutdown has been initiated"""
    return _shutdown_initiated