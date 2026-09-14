import asyncio
import inspect
import json
from pathlib import Path

from fastmcp import FastMCP

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.server import build_server
from carla_mcp.bridge.tools import register_all

SNAPSHOT = Path(__file__).parent / "data" / "tool_surface.json"


def _params(fn):
    """Each parameter in order, with its default pinned (or marked required)."""
    out = []
    for p in inspect.signature(fn).parameters.values():
        if p.default is inspect.Parameter.empty:
            out.append({"name": p.name, "required": True})
        else:
            out.append({"name": p.name, "default": p.default})
    return out


def _surface():
    b = Bridge.for_tests()
    specs = register_all(FastMCP("surface-snapshot"), b)
    return {s.name: {"params": _params(s.fn), "annotations": s.annotations} for s in specs}


def test_surface_matches_checked_in_snapshot():
    """Changing the tool surface is deliberate: update tests/data/tool_surface.json."""
    assert _surface() == json.loads(SNAPSHOT.read_text())


def test_snapshot_pins_safety_relevant_defaults():
    snap = json.loads(SNAPSHOT.read_text())
    assert snap["rig_reset_routing"]["params"] == [{"name": "dry_run", "default": False}]
    assert snap["session_save"]["params"] == [{"name": "name", "required": True},
                                              {"name": "overwrite", "default": False}]


def test_flipped_defaults_do_not_match_the_snapshot():
    async def rig_reset_routing(dry_run: bool = True): ...
    async def session_save(name: str, overwrite: bool = True): ...

    snap = json.loads(SNAPSHOT.read_text())
    assert _params(rig_reset_routing) != snap["rig_reset_routing"]["params"]
    assert _params(session_save) != snap["session_save"]["params"]


def test_server_exposes_exactly_the_specs():
    b = Bridge.for_tests()
    mcp = build_server(b)
    tools = asyncio.run(mcp.get_tools())
    assert set(tools) == set(_surface())
