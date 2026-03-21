#!/usr/bin/env python3
"""
Stdio-to-SSE bridge for Carla MCP Server.

Always-on MCP proxy that Claude Code connects to via stdio. Manages
Carla's lifecycle (start/stop/restart) and dynamically registers
Carla's tools when the engine becomes reachable.

The bridge exposes:
  - carla_start / carla_stop / carla_restart - lifecycle management
  - carla_status - check if Carla is running
  - (dynamic) all Carla tools are registered/unregistered automatically

Usage in .mcp.json:
{
    "mcpServers": {
        "carla-mcp": {
            "command": "uv",
            "args": ["run", "python3", "source/frontend/carla_mcp/mcp_stdio_bridge.py"],
            "cwd": "/home/michael/carla-mcp-fork"
        }
    }
}
"""

import asyncio
import atexit
import os
import sys
import subprocess
from pathlib import Path

from fastmcp import FastMCP

from carla_mcp.tool_proxy import discover_and_register, unregister_all

CARLA_PORT = os.getenv("CARLA_MCP_PORT", "3001")
CARLA_HOST = os.getenv("CARLA_MCP_HOST", "127.0.0.1")
CARLA_SSE_URL = f"http://{CARLA_HOST}:{CARLA_PORT}/sse"

# Path to carla.py - relative to this file
_THIS_DIR = Path(__file__).resolve().parent
CARLA_SCRIPT = _THIS_DIR.parent / "carla.py"
CARLA_FRONTEND_DIR = _THIS_DIR.parent

bridge = FastMCP("Carla MCP Bridge")

# Track the Carla process we launched
_carla_process: subprocess.Popen | None = None
_carla_log_file = None


def _is_carla_running() -> bool:
    """Check if our managed Carla process is running."""
    global _carla_process
    if _carla_process is not None:
        if _carla_process.poll() is None:
            return True
        _carla_process = None
    return False


def _is_carla_reachable() -> bool:
    """Quick check if Carla's MCP port is responding."""
    import socket
    try:
        with socket.create_connection((CARLA_HOST, int(CARLA_PORT)), timeout=1):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


async def _start_carla() -> str:
    """Start Carla (internal helper)."""
    global _carla_process, _carla_log_file

    if _is_carla_running() or _is_carla_reachable():
        count = await discover_and_register(bridge, CARLA_SSE_URL, prefix="carla")
        src = f"managed (PID {_carla_process.pid})" if _is_carla_running() else "external"
        return f"Carla is already running ({src}). {count} tools registered."

    env = os.environ.copy()
    env["CARLA_MCP_PORT"] = str(CARLA_PORT)

    # Use /usr/bin/python3 (system Python with PyQt5), not the venv python
    _carla_log_file = open("/tmp/carla-mcp.log", "w")
    _carla_process = subprocess.Popen(
        ["pw-jack", "/usr/bin/python3", str(CARLA_SCRIPT)],
        env=env,
        cwd=str(CARLA_FRONTEND_DIR),
        stdout=_carla_log_file,
        stderr=_carla_log_file,
    )

    # Wait for MCP to become reachable
    for i in range(15):
        await asyncio.sleep(1)
        if _is_carla_reachable():
            # Carla may accept connections before tools are registered; retry briefly
            for _ in range(5):
                count = await discover_and_register(bridge, CARLA_SSE_URL, prefix="carla")
                if count > 0:
                    break
                await asyncio.sleep(1)
            return f"Carla started (PID {_carla_process.pid}). MCP server ready on port {CARLA_PORT}. {count} tools registered."
        if _carla_process.poll() is not None:
            return f"Carla process exited with code {_carla_process.returncode}. Check logs."

    return f"Carla started (PID {_carla_process.pid}) but MCP server not yet reachable. It may still be initializing."


async def _stop_carla() -> str:
    """Stop Carla (internal helper)."""
    global _carla_process, _carla_log_file

    if _carla_process is None or _carla_process.poll() is not None:
        _carla_process = None
        return "No managed Carla process to stop."

    unregister_all(bridge, prefix="carla")
    _carla_process.terminate()
    try:
        _carla_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _carla_process.kill()
        _carla_process.wait()

    pid = _carla_process.pid
    _carla_process = None

    if _carla_log_file is not None:
        _carla_log_file.close()
        _carla_log_file = None

    return f"Carla stopped (PID {pid})."


@bridge.tool()
async def carla_start() -> str:
    """
    Start the Carla audio plugin host.
    Launches Carla with PipeWire/JACK support and MCP server enabled.
    """
    return await _start_carla()


@bridge.tool()
async def carla_stop() -> str:
    """Stop the running Carla instance."""
    return await _stop_carla()


@bridge.tool()
async def carla_restart() -> str:
    """Restart Carla (stop then start)."""
    stop_msg = await _stop_carla()
    await asyncio.sleep(1)
    start_msg = await _start_carla()
    return f"{stop_msg}\n{start_msg}"


@bridge.tool()
async def carla_status() -> str:
    """Check if Carla is running and its MCP server is reachable."""
    process_running = _is_carla_running()
    reachable = _is_carla_reachable()

    if reachable:
        src = f"managed (PID {_carla_process.pid})" if process_running else "external"
        return f"Carla is running ({src}). MCP reachable at {CARLA_SSE_URL}"
    elif process_running:
        return f"Carla process running (PID {_carla_process.pid}) but MCP not reachable yet."
    else:
        return "Carla is not running. Use carla_start to launch it."


def _atexit_cleanup():
    """Ensure Carla is terminated on exit."""
    global _carla_process, _carla_log_file
    if _carla_process is not None and _carla_process.poll() is None:
        _carla_process.terminate()
        try:
            _carla_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _carla_process.kill()
            _carla_process.wait()
        _carla_process = None
    if _carla_log_file is not None:
        _carla_log_file.close()
        _carla_log_file = None


atexit.register(_atexit_cleanup)


def main():
    bridge.run(transport="stdio")


if __name__ == "__main__":
    main()
