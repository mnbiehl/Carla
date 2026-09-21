"""Carla MCP — bridge, backends, worker and rig packages.

Deliberately import-free: the worker package is loaded inside Carla's system
Python, which has neither fastmcp nor numpy.  Import submodules explicitly.
"""

__version__ = "0.3.0"