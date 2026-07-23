"""
Rig graph package: in-memory rig graph state and stable plugin handle layer.

Public names
------------
graph    — Effect, Node, Edge, RigGraph, RuntimeUnit, NODE_KINDS, EDGE_KINDS
handles  — HANDLE_KEY, stamp_handle, resolve_handle, read_handle
describe — describe_rig
"""

from carla_mcp.rig.graph import (
    EDGE_KINDS, NODE_KINDS, Effect, Node, Edge, RigGraph, RuntimeUnit,
)
from carla_mcp.rig.handles import HANDLE_KEY, stamp_handle, resolve_handle, read_handle
from carla_mcp.rig.describe import describe_rig
from carla_mcp.rig.remote import RemoteInstance
from carla_mcp.rig.controller import RigController
from carla_mcp.rig.register import register_rig_tools

__all__ = [
    "Effect",
    "Node",
    "Edge",
    "RigGraph",
    "RuntimeUnit",
    "NODE_KINDS",
    "EDGE_KINDS",
    "HANDLE_KEY",
    "stamp_handle",
    "resolve_handle",
    "read_handle",
    "describe_rig",
    "RemoteInstance",
    "RigController",
    "register_rig_tools",
]
