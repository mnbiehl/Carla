import asyncio

import pytest

pytestmark = pytest.mark.live


def test_rig_up_state_down(live_bridge):
    b, tools = live_bridge
    up = asyncio.run(tools["rig_up"].fn())
    assert up["ok"], up
    # The smoke test proves the bridge can launch Carla, so the rig must be idle:
    # an adopted Carla shows up in already_up and fails here on purpose.
    assert "carla:main" in up["result"]["started"], (
        "carla:main was not started by this bridge (already running?)", up)
    state = asyncio.run(tools["rig_state"].fn(detail="io"))
    assert state["ok"], state
    assert state["result"]["versions"]["carla"] not in ("down", "unknown"), state["result"]["versions"]
    assert any(p.startswith("loopers:") for p in state["result"]["io"]["outputs"]), "loopers ports missing"
    down = asyncio.run(tools["rig_down"].fn())
    assert down["ok"] and down["result"]["report"].startswith("OK"), down
