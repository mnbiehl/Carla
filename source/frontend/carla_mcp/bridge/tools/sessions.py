# source/frontend/carla_mcp/bridge/tools/sessions.py  (placeholder; Task 16 replaces it)
from __future__ import annotations
from typing import List
from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.tools import ToolSpec


async def load_session_into(b: Bridge, name: str) -> List[str]:
    raise NotImplementedError("Task 16")


def build(b: Bridge) -> List[ToolSpec]:
    return []
