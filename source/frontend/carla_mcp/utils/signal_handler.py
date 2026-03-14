"""
Signal handling utilities for Carla MCP Server

Provides clean shutdown handling for the MCP server.
"""

import logging
import signal
import sys

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
    # Graceful shutdown - don't force exit, let parent handle cleanup
    try:
        print("👋 MCP server shutdown complete")
        sys.stdout.flush()
    except (ValueError, OSError):
        pass
    # Don't call os._exit(0) - this can crash the parent process
    # Let the parent Carla application handle the shutdown sequence


# Expose shutdown event for external modules
def shutdown_event():
    """Check if shutdown has been initiated"""
    return _shutdown_initiated