import asyncio
import os

import pytest

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.tools import lifecycle

pytestmark = pytest.mark.live


@pytest.fixture
def live_bridge():
    if os.getenv("CARLA_MCP_LIVE") != "1":
        pytest.skip(reason="set CARLA_MCP_LIVE=1 (needs PipeWire, Carla build, loopers binary)")
    b = Bridge.from_env()
    tools = {t.name: t for t in lifecycle.build(b)}
    yield b, tools
    asyncio.run(tools["rig_down"].fn())
