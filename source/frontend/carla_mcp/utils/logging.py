"""
Logging utilities for Carla MCP Server

Enhanced logging configuration and utilities.
"""

import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO", debug: bool = False) -> logging.Logger:
    """
    Set up logging configuration for the Carla MCP Server
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        debug: Enable debug mode with more verbose output
        
    Returns:
        Logger instance for the main module
    """
    # Convert level string to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Save original stderr in case Carla redirects it
    import sys
    original_stderr = sys.__stderr__
    
    # Don't mess with root logger - just create our own handler
    logger = logging.getLogger("carla_mcp")
    
    # Remove any existing handlers on our logger
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create fresh handler with our stderr
    handler = logging.StreamHandler(original_stderr)
    handler.setLevel(log_level)
    
    # Create formatter
    fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s' if debug else '%(levelname)s:%(name)s:%(message)s'
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    
    # Configure our logger only
    logger.setLevel(log_level)
    logger.addHandler(handler)
    logger.propagate = False  # Don't propagate to root logger
    
    if debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module
    
    Args:
        name: Module name for the logger
        
    Returns:
        Logger instance for the specified module
    """
    return logging.getLogger(f"carla_mcp.{name}")