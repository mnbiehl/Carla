#!/usr/bin/env python3
"""
Main entry point for Carla MCP Dispatcher
"""

import asyncio
import logging
import sys
from .dispatcher_server import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested... exiting")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)