#!/usr/bin/env python3
"""
Carla Launcher - Wrapper script for running Carla from source tree

This script sets up the proper Python path and working directory
so that Carla can run from the poetry environment.
"""

import os
import sys
from pathlib import Path

def main():
    """Launch Carla with proper environment setup"""
    # Get the directory containing this script
    script_dir = Path(__file__).parent
    frontend_dir = script_dir / "source" / "frontend"
    
    # Add the frontend directory to Python path
    sys.path.insert(0, str(frontend_dir))
    
    # Change to the frontend directory so relative imports work
    original_cwd = os.getcwd()
    os.chdir(frontend_dir)
    
    try:
        # Import and run the main carla function
        from carla import main as carla_main
        carla_main()
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

if __name__ == "__main__":
    main()