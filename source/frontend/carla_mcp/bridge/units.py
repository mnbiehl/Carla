"""Start/stop the rig's processes with readiness polling. None = success."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from carla_mcp.backends import pw_link
from carla_mcp.backends.processes import UnitSpec, a2j_running, ports_present, tcp_reachable
from carla_mcp.bridge.app import Bridge

CARLA_READY_TIMEOUT_S = 20.0
LOOPER_READY_TIMEOUT_S = 10.0
POLL_S = 0.5


async def _wait(predicate, timeout_s: float, still_alive) -> Optional[str]:
    waited = 0.0
    while waited < timeout_s:
        if predicate():
            return None
        if not still_alive():
            return "process exited before becoming ready"
        await asyncio.sleep(POLL_S)
        waited += POLL_S
    return f"not ready after {timeout_s:.0f}s"


async def start_carla_main(b: Bridge) -> Optional[str]:
    port = b.config.carla_rpc_port
    if tcp_reachable("127.0.0.1", port):
        return None
    env = dict(os.environ)
    env["CARLA_RPC_PORT"] = str(port)
    env.setdefault("CARLA_MCP_PORT", b.config.carla_sse_url.rsplit(":", 1)[1].split("/")[0])
    b.processes.spawn(UnitSpec(
        name="carla:main",
        argv=["pw-jack", b.config.carla_python, str(b.config.frontend_dir / "carla.py")],
        cwd=str(b.config.frontend_dir),
        env=env,
    ))
    err = await _wait(lambda: tcp_reachable("127.0.0.1", port), CARLA_READY_TIMEOUT_S,
                      lambda: b.processes.is_running("carla:main"))
    return None if err is None else f"carla:main {err} (see {b.config.log_dir / 'carla:main.log'})"


async def stop_carla_main(b: Bridge) -> Optional[str]:
    return b.processes.stop("carla:main")


async def start_looper_engine(b: Bridge) -> Optional[str]:
    if ports_present("loopers:", pw_link.list_outputs):
        return None
    b.processes.spawn(UnitSpec(
        name="looper:engine",
        argv=["pw-jack", b.config.loopers_path, "--managed",
              "--remote-json-port", str(b.config.looper_port)],
        env=dict(os.environ),
    ))
    err = await _wait(lambda: ports_present("loopers:", pw_link.list_outputs),
                      LOOPER_READY_TIMEOUT_S, lambda: b.processes.is_running("looper:engine"))
    return None if err is None else f"looper:engine {err} (see {b.config.log_dir / 'looper:engine.log'})"


async def stop_looper_engine(b: Bridge) -> Optional[str]:
    return b.processes.stop("looper:engine")


def start_a2j(b: Bridge) -> Optional[str]:
    if a2j_running():
        return None
    try:
        b.processes.spawn(UnitSpec(name="a2j", argv=["a2jmidid", "-e"]))
    except FileNotFoundError:
        return "a2jmidid not installed"
    return None


def stop_a2j(b: Bridge) -> Optional[str]:
    return b.processes.stop("a2j")
