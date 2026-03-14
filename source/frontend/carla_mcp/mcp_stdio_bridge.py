#!/usr/bin/env python3
"""
Stdio-to-SSE bridge for Carla MCP Server.

Always-on MCP proxy that Claude Code connects to via stdio. Manages
Carla's lifecycle (start/stop/restart) and forwards tool calls to
Carla's SSE MCP server on demand.

The bridge exposes:
  - carla_start / carla_stop / carla_restart - lifecycle management
  - carla_status - check if Carla is running
  - carla_list_tools - discover available Carla tools
  - carla - forward any tool call to Carla

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

import os
import sys
import json
import signal
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from mcp.client.sse import sse_client
from mcp import ClientSession
from mcp.types import TextContent

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


@asynccontextmanager
async def _carla_session():
    """Connect to Carla's SSE MCP server on demand."""
    async with sse_client(CARLA_SSE_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@bridge.tool()
async def carla_start() -> str:
    """
    Start the Carla audio plugin host.
    Launches Carla with PipeWire/JACK support and MCP server enabled.
    """
    global _carla_process

    if _is_carla_running():
        return "Carla is already running."

    if _is_carla_reachable():
        return "Carla is already running (started externally)."

    env = os.environ.copy()
    env["CARLA_MCP_PORT"] = str(CARLA_PORT)

    # Use /usr/bin/python3 (system Python with PyQt5), not the venv python
    log_file = open("/tmp/carla-mcp.log", "w")
    _carla_process = subprocess.Popen(
        ["pw-jack", "/usr/bin/python3", str(CARLA_SCRIPT)],
        env=env,
        cwd=str(CARLA_FRONTEND_DIR),
        stdout=log_file,
        stderr=log_file,
    )

    # Wait for MCP to become reachable
    import time
    for i in range(15):
        time.sleep(1)
        if _is_carla_reachable():
            return f"Carla started (PID {_carla_process.pid}). MCP server ready on port {CARLA_PORT}."
        if _carla_process.poll() is not None:
            return f"Carla process exited with code {_carla_process.returncode}. Check logs."

    return f"Carla started (PID {_carla_process.pid}) but MCP server not yet reachable. It may still be initializing."


@bridge.tool()
async def carla_stop() -> str:
    """Stop the running Carla instance."""
    global _carla_process

    if _carla_process is None or _carla_process.poll() is not None:
        _carla_process = None
        return "No managed Carla process to stop."

    _carla_process.terminate()
    try:
        _carla_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _carla_process.kill()

    pid = _carla_process.pid
    _carla_process = None
    return f"Carla stopped (PID {pid})."


@bridge.tool()
async def carla_restart() -> str:
    """Restart Carla (stop then start)."""
    stop_msg = await carla_stop()
    import time
    time.sleep(1)
    start_msg = await carla_start()
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


@bridge.tool()
async def carla_list_tools() -> str:
    """
    List all available tools on the running Carla instance.
    Call this to see what Carla tools you can use with the `carla` tool.
    """
    try:
        async with _carla_session() as session:
            result = await session.list_tools()
            lines = [f"Carla is running. {len(result.tools)} tools available:\n"]
            for t in result.tools:
                desc = (t.description or "").split("\n")[0][:100]
                params = t.inputSchema.get("properties", {}) if t.inputSchema else {}
                required = t.inputSchema.get("required", []) if t.inputSchema else []
                if params:
                    param_strs = []
                    for p in params:
                        param_strs.append(f"{p}*" if p in required else p)
                    sig = f"({', '.join(param_strs)})"
                else:
                    sig = "()"
                lines.append(f"  {t.name}{sig} - {desc}")
            return "\n".join(lines)
    except Exception as e:
        return f"Carla is not reachable. Use carla_start to launch it.\n\nError: {e}"


@bridge.tool()
async def carla(tool: str, arguments: str = "{}") -> str:
    """
    Call any tool on the running Carla instance.

    Use `carla_list_tools` first to see available tools and their parameters.

    Args:
        tool: Name of the Carla tool (e.g. "search_plugins", "create_effects_chain")
        arguments: JSON object with tool arguments (e.g. '{"query": "reverb"}')

    Returns:
        Result from Carla, or error message if Carla is not running
    """
    try:
        args = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError as e:
        return f"Invalid JSON in arguments: {e}\n\nPass arguments as a JSON object string."

    try:
        async with _carla_session() as session:
            result = await session.call_tool(tool, args)
            parts = []
            for content in result.content:
                if isinstance(content, TextContent):
                    parts.append(content.text)
                else:
                    parts.append(str(content))
            return "\n".join(parts) if parts else "OK"
    except Exception as e:
        return f"Error calling '{tool}': {e}\n\nIs Carla running? Use carla_status to check."


def main():
    bridge.run(transport="stdio")


if __name__ == "__main__":
    main()
