"""looper_save_session_at must wait for project.loopers to actually land
with a fresh save_time, not trust SaveSessionAt's enqueue ack.

loopers' remote.rs replies {"ok": true} as soon as the command is queued,
before the (potentially 100+ MB) audio is serialized and project.loopers is
written (loopers-engine/src/session.rs). All timings here are monkeypatched
to be fast; no network, no live rig.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock

from carla_mcp.backends.rpc import RpcError
from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.ops import BridgeOps


def _ops(tmp_path, poll_s=0.01, wait_s=0.2):
    b = Bridge.for_tests()
    b.looper.save_session_at = AsyncMock(return_value={"ok": True})
    ops = BridgeOps(b)
    ops._looper_save_poll_s = poll_s
    ops._looper_save_wait_s = wait_s
    return ops


def _write_project(path, save_time_ms):
    path.write_text(json.dumps({"save_time": save_time_ms, "loopers": []}))


def test_waits_for_file_to_appear_with_fresh_save_time(tmp_path):
    session_dir = tmp_path / "looper"
    session_dir.mkdir()
    project = session_dir / "project.loopers"

    async def run():
        async def delayed_write():
            await asyncio.sleep(0.05)
            _write_project(project, int(time.time() * 1000))

        task = asyncio.ensure_future(delayed_write())
        try:
            result = await ops.looper_save_session_at(str(session_dir))
        finally:
            await task
        return result

    ops = _ops(tmp_path)
    assert not project.exists()
    result = asyncio.run(run())
    assert result is None
    assert project.exists()


def test_stale_project_file_times_out_and_reports_error(tmp_path):
    """Regression test: against the pre-fix code (which returned as soon as
    the ack came back) this passes with result is None immediately, without
    ever looking at project.loopers' age. That is the bug."""
    session_dir = tmp_path / "looper"
    session_dir.mkdir()
    project = session_dir / "project.loopers"
    stale_ms = int(time.time() * 1000) - 60_000  # a minute old, from a prior save
    _write_project(project, stale_ms)

    ops = _ops(tmp_path, poll_s=0.01, wait_s=0.1)
    result = asyncio.run(ops.looper_save_session_at(str(session_dir)))

    assert result is not None
    assert "looper save did not complete within" in result
    assert str(project) in result or f"{session_dir}/project.loopers" in result


def test_partial_json_then_completed_is_accepted(tmp_path):
    session_dir = tmp_path / "looper"
    session_dir.mkdir()
    project = session_dir / "project.loopers"
    # Simulate an in-progress writeln!: truncated JSON.
    project.write_text('{"save_time": ')

    async def run():
        async def finish_write():
            await asyncio.sleep(0.05)
            _write_project(project, int(time.time() * 1000))

        task = asyncio.ensure_future(finish_write())
        try:
            result = await ops.looper_save_session_at(str(session_dir))
        finally:
            await task
        return result

    ops = _ops(tmp_path)
    result = asyncio.run(run())
    assert result is None


def test_send_rpc_error_returns_immediately_without_polling(tmp_path):
    session_dir = tmp_path / "looper"
    session_dir.mkdir()  # no project.loopers at all

    ops = _ops(tmp_path, poll_s=10.0, wait_s=10.0)  # would hang if it ever polled
    ops.b.looper.save_session_at = AsyncMock(side_effect=RpcError("internal", "not connected"))

    async def run():
        return await asyncio.wait_for(ops.looper_save_session_at(str(session_dir)), timeout=1.0)

    result = asyncio.run(run())
    assert result is not None
    assert "not connected" in result
