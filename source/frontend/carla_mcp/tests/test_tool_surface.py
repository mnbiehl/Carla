import asyncio
import inspect
import json
from pathlib import Path

from fastmcp import FastMCP

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.server import build_server
from carla_mcp.bridge.tools import register_all

SNAPSHOT = Path(__file__).parent / "data" / "tool_surface.json"


def _surface():
    b = Bridge.for_tests()
    specs = register_all(FastMCP("surface-snapshot"), b)
    return {
        s.name: {"params": list(inspect.signature(s.fn).parameters), "annotations": s.annotations}
        for s in specs
    }


def test_surface_matches_checked_in_snapshot():
    """Changing the tool surface is deliberate: update tests/data/tool_surface.json."""
    assert _surface() == json.loads(SNAPSHOT.read_text())


def test_server_exposes_exactly_the_specs():
    b = Bridge.for_tests()
    mcp = build_server(b)
    tools = asyncio.run(mcp.get_tools())
    assert set(tools) == set(_surface())
