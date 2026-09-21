"""Start/stop the rig's processes with readiness polling. None = success.

Probes (TCP, pw-link, pgrep) and process waits block; the async helpers run
them through `asyncio.to_thread` so readiness polling never stalls the loop.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Callable, Optional, Tuple
from urllib.parse import urlsplit

from carla_mcp.backends import pw_link
from carla_mcp.backends.processes import (
    UnitSpec, a2j_running, carla_gui_running, ports_present, tcp_reachable,
)
from carla_mcp.bridge.app import Bridge

CARLA_READY_TIMEOUT_S = 20.0
LOOPER_READY_TIMEOUT_S = 10.0
POLL_S = 0.5

NOT_STARTED_BY_THIS_BRIDGE = "not started by this bridge; left running"


async def _stop_owned(b: Bridge, name: str, still_up: Callable[[], bool]) -> Optional[str]:
    """Stop `name` only if this bridge's ProcessManager spawned it. A unit that is
    up but not ours (e.g. adopted after a bridge restart) is left running and
    reported; a unit that is already down is success. No re-adoption by pid."""
    if await asyncio.to_thread(b.processes.stop, name):
        return None
    return NOT_STARTED_BY_THIS_BRIDGE if await asyncio.to_thread(still_up) else None


async def _wait(predicate, timeout_s: float, still_alive) -> Optional[str]:
    """Poll `predicate` until true, the process dies, or `timeout_s` of wall
    clock passes (a monotonic deadline: probe time counts, not just sleeps)."""
    deadline = time.monotonic() + timeout_s
    while True:
        if await asyncio.to_thread(predicate):
            return None
        if not await asyncio.to_thread(still_alive):
            return "process exited before becoming ready"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return f"not ready after {timeout_s:.0f}s"
        await asyncio.sleep(min(POLL_S, remaining))


def _sse_host_port(b: Bridge) -> Tuple[str, int]:
    parts = urlsplit(b.config.carla_sse_url)
    return parts.hostname or "127.0.0.1", parts.port or 80


def carla_running_without_worker(b: Bridge) -> bool:
    """Carla is up but its RPC port is closed: a carla.py process exists, or the
    legacy MCP SSE port answers. Only meaningful once the RPC probe failed."""
    return carla_gui_running() or tcp_reachable(*_sse_host_port(b))


async def start_carla_main(b: Bridge) -> Optional[str]:
    port = b.config.carla_rpc_port
    if await asyncio.to_thread(tcp_reachable, "127.0.0.1", port):
        return None
    if await asyncio.to_thread(carla_running_without_worker, b):
        return (f"Carla is running without the RPC worker on {port}; not starting a second "
                "instance (restart Carla from this branch)")
    env = dict(os.environ)
    env["CARLA_RPC_PORT"] = str(port)
    env.setdefault("CARLA_MCP_PORT", str(_sse_host_port(b)[1]))
    try:
        b.processes.spawn(UnitSpec(
            name="carla:main",
            argv=["pw-jack", b.config.carla_python, str(b.config.frontend_dir / "carla.py")],
            cwd=str(b.config.frontend_dir),
            env=env,
        ))
    except OSError as exc:
        return f"carla:main spawn failed: {exc}"
    err = await _wait(lambda: tcp_reachable("127.0.0.1", port), CARLA_READY_TIMEOUT_S,
                      lambda: b.processes.is_running("carla:main"))
    return None if err is None else f"carla:main {err} (see {b.config.log_dir / 'carla:main.log'})"


async def stop_carla_main(b: Bridge) -> Optional[str]:
    return await _stop_owned(b, "carla:main", lambda: tcp_reachable("127.0.0.1", b.config.carla_rpc_port))


async def start_looper_engine(b: Bridge) -> Optional[str]:
    if await asyncio.to_thread(ports_present, "loopers:", pw_link.list_outputs):
        return None
    try:
        b.processes.spawn(UnitSpec(
            name="looper:engine",
            argv=["pw-jack", b.config.loopers_path, "--managed",
                  "--remote-json-port", str(b.config.looper_port)],
            env=dict(os.environ),
        ))
    except OSError as exc:
        return f"looper:engine spawn failed: {exc}"
    err = await _wait(lambda: ports_present("loopers:", pw_link.list_outputs),
                      LOOPER_READY_TIMEOUT_S, lambda: b.processes.is_running("looper:engine"))
    return None if err is None else f"looper:engine {err} (see {b.config.log_dir / 'looper:engine.log'})"


async def stop_looper_engine(b: Bridge) -> Optional[str]:
    return await _stop_owned(b, "looper:engine", lambda: ports_present("loopers:", pw_link.list_outputs))


def start_a2j(b: Bridge) -> Optional[str]:
    if a2j_running():
        return None
    try:
        b.processes.spawn(UnitSpec(name="a2j", argv=["a2jmidid", "-e"]))
    except FileNotFoundError:
        return "a2jmidid not installed"
    except OSError as exc:
        return f"a2j spawn failed: {exc}"
    return None


async def stop_a2j(b: Bridge) -> Optional[str]:
    return await _stop_owned(b, "a2j", a2j_running)
