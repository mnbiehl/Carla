"""FastMCP server factory and stdio entry point."""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.tools import register_all

INSTRUCTIONS = (
    "Rig conductor for a live looping setup (loopers + Carla). Call rig_state first. "
    "Tools annotated destructive affect a performance in progress: ask before using them."
)


def build_server(bridge: Bridge) -> FastMCP:
    mcp = FastMCP("carla-rig", instructions=INSTRUCTIONS)
    register_all(mcp, bridge)
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    build_server(Bridge.from_env()).run(transport="stdio")
