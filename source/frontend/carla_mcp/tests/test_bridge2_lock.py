"""Mutating tools are serialized per Bridge and fail fast when another holds the lock."""

import asyncio
from unittest.mock import AsyncMock, patch

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.tools import BUSY_MESSAGE, lifecycle, sessions
from carla_mcp.rig.observe import ObservedState

EMPTY = ObservedState(links=[], output_ports=[], input_ports=[], unit_status={})


def _bridge():
    b = Bridge.for_tests()
    b.looper.loopers = AsyncMock(return_value=[])
    b.carla.version = AsyncMock(return_value={"worker": "w"})
    return b


def _tools(b):
    return {t.name: t for t in lifecycle.build(b) + sessions.build(b)}


def _is_busy(reply):
    return (reply["ok"] is False and reply["error"]["type"] == "validation"
            and reply["error"]["message"] == BUSY_MESSAGE)


def test_bridges_have_independent_locks():
    a, b = Bridge.for_tests(), Bridge.for_tests()
    assert isinstance(a.lock, asyncio.Lock) and a.lock is not b.lock


def test_mutating_tools_fail_fast_while_a_save_holds_the_lock():
    b = _bridge()
    t = _tools(b)

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocking_save(name, sdir, ops):
            entered.set()
            await release.wait()
            (sdir / "looper").mkdir(parents=True, exist_ok=True)
            return "OK\n"

        stop = AsyncMock(return_value="OK\n")
        with patch("carla_mcp.bridge.tools.sessions.do_save", new=blocking_save), \
             patch("carla_mcp.bridge.tools.lifecycle.do_stop", new=stop), \
             patch("carla_mcp.bridge.tools.lifecycle.do_routing_reset", new=AsyncMock(return_value="OK")), \
             patch("carla_mcp.bridge.tools.lifecycle.BridgeOps.observe", new=AsyncMock(return_value=EMPTY)):
            save = asyncio.ensure_future(t["session_save"].fn("tues"))
            await asyncio.wait_for(entered.wait(), 2)
            assert b.lock.locked()

            busy = {
                "rig_down": await t["rig_down"].fn(),
                "rig_up": await t["rig_up"].fn(),
                "rig_reset_routing": await t["rig_reset_routing"].fn(),
                "session_save": await t["session_save"].fn("other"),
                "session_load": await t["session_load"].fn("tues"),
            }
            stop.assert_not_awaited()  # rig_down never reached the rig
            # Read-only calls are not serialized.
            state = await t["rig_state"].fn()
            listing = await t["session_list"].fn()
            dry = await t["rig_reset_routing"].fn(dry_run=True)

            release.set()
            saved = await asyncio.wait_for(save, 2)
            after = await t["rig_down"].fn()
        return busy, state, listing, dry, saved, after, stop

    busy, state, listing, dry, saved, after, stop = asyncio.run(run())
    assert all(_is_busy(r) for r in busy.values()), busy
    assert state["ok"] and listing["ok"] and dry["ok"] and dry["result"]["dry_run"] is True
    assert saved["ok"] and saved["result"]["report"] == "OK\n"
    assert after["ok"] and after["result"]["report"] == "OK\n"
    stop.assert_awaited_once()
    assert not b.lock.locked()


def test_lock_is_released_when_a_mutating_tool_fails():
    b = _bridge()
    t = _tools(b)
    with patch("carla_mcp.bridge.tools.lifecycle.do_stop", new=AsyncMock(side_effect=RuntimeError("boom"))):
        out = asyncio.run(t["rig_down"].fn())
    assert out["ok"] is False and out["error"]["type"] == "internal"
    assert not b.lock.locked()
    missing = asyncio.run(t["session_load"].fn("ghost"))
    assert missing["error"]["type"] == "not_found" and not b.lock.locked()
