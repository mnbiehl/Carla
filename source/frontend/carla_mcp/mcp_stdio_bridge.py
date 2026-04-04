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
import json
import os
import sys
import subprocess
from pathlib import Path

from fastmcp import FastMCP
from mcp.client.sse import sse_client
from mcp import ClientSession

from carla_mcp.tool_proxy import discover_and_register, unregister_all

CARLA_PORT = os.getenv("CARLA_MCP_PORT", "3001")
CARLA_HOST = os.getenv("CARLA_MCP_HOST", "127.0.0.1")
CARLA_SSE_URL = f"http://{CARLA_HOST}:{CARLA_PORT}/sse"

# Path constants
_THIS_DIR = Path(__file__).resolve().parent
CARLA_FRONTEND_DIR = _THIS_DIR.parent

# Looper MCP server configuration
LOOPER_MCP_PORT = os.getenv("LOOPER_MCP_PORT", "3002")
LOOPER_MCP_HOST = os.getenv("LOOPER_MCP_HOST", "127.0.0.1")
LOOPER_SSE_URL = f"http://{LOOPER_MCP_HOST}:{LOOPER_MCP_PORT}/sse"
LOOPER_MCP_SCRIPT = _THIS_DIR.parent / "looper_mcp" / "main.py"

RIG_SESSION_DIR = Path.home() / ".config" / "rig-sessions"


def _build_rig_manifest(
    carla_running: bool,
    looper_running: bool,
    carla_session: str = "",
    looper_session: str = "",
) -> dict:
    return {
        "version": 1,
        "backends": {
            "carla": {"running": carla_running, "session": carla_session},
            "looper": {"running": looper_running, "session": looper_session},
        },
    }


bridge = FastMCP("Carla MCP Bridge")

# Track the Carla process we launched
_carla_process: subprocess.Popen | None = None
_carla_log_file = None

# Looper engine (Rust binary) configuration
LOOPERS_PATH = os.getenv("LOOPERS_PATH", str(Path(__file__).resolve().parent.parent.parent.parent.parent / "looperdooper" / "target" / "release" / "loopers"))

# Track the Looper MCP process we launched
_looper_process: subprocess.Popen | None = None
_looper_log_file = None

# Track the Looper engine process (Rust binary)
_looper_engine_process: subprocess.Popen | None = None
_looper_engine_log_file = None


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

    # Launch carla.py (the Carla GUI + engine + MCP SSE server)
    # The bridge proxies tool calls to this SSE server — it needs the engine running
    carla_script = str(CARLA_FRONTEND_DIR / "carla.py")
    _carla_log_file = open("/tmp/carla-mcp.log", "w")
    _carla_process = subprocess.Popen(
        ["pw-jack", "/usr/bin/python3", carla_script],
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


def _is_looper_running() -> bool:
    """Check if both the Looper engine and MCP processes are running."""
    global _looper_process, _looper_engine_process
    mcp_alive = False
    engine_alive = False
    if _looper_process is not None:
        if _looper_process.poll() is None:
            mcp_alive = True
        else:
            _looper_process = None
    if _looper_engine_process is not None:
        if _looper_engine_process.poll() is None:
            engine_alive = True
        else:
            _looper_engine_process = None
    return mcp_alive and engine_alive


def _is_looper_reachable() -> bool:
    """Quick check if Looper's MCP port is responding."""
    import socket
    try:
        with socket.create_connection((LOOPER_MCP_HOST, int(LOOPER_MCP_PORT)), timeout=1):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


async def _start_looper() -> str:
    """Start the Looper engine and MCP server (internal helper)."""
    global _looper_process, _looper_log_file
    global _looper_engine_process, _looper_engine_log_file

    if _is_looper_running() or _is_looper_reachable():
        count = await discover_and_register(bridge, LOOPER_SSE_URL, prefix="looper")
        src = f"managed (PID {_looper_process.pid})" if _is_looper_running() else "external"
        return f"Looper is already running ({src}). {count} tools registered."

    env = os.environ.copy()
    env["LOOPER_MCP_PORT"] = str(LOOPER_MCP_PORT)

    # Step 1: Launch the loopers audio engine via pw-jack
    _looper_engine_log_file = open("/tmp/looper-engine.log", "w")
    _looper_engine_process = subprocess.Popen(
        ["pw-jack", LOOPERS_PATH],
        env=env,
        stdout=_looper_engine_log_file,
        stderr=_looper_engine_log_file,
    )

    # Poll for JACK ports to appear (1s interval, 10s timeout)
    engine_ready = False
    for _ in range(10):
        await asyncio.sleep(1)
        if _looper_engine_process.poll() is not None:
            return (
                f"Looper engine exited with code {_looper_engine_process.returncode}. "
                "Check /tmp/looper-engine.log."
            )
        try:
            result = subprocess.run(
                ["pw-link", "-o"],
                capture_output=True, text=True, timeout=3,
            )
            if "loopers" in result.stdout or "looperdooper" in result.stdout:
                engine_ready = True
                break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if not engine_ready:
        return (
            f"Looper engine started (PID {_looper_engine_process.pid}) "
            "but JACK ports did not appear within 10s."
        )

    # Step 2: Launch the looper MCP server
    _looper_log_file = open("/tmp/looper-mcp.log", "w")
    _looper_process = subprocess.Popen(
        ["uv", "run", "python3", str(LOOPER_MCP_SCRIPT)],
        env=env,
        cwd=str(CARLA_FRONTEND_DIR),
        stdout=_looper_log_file,
        stderr=_looper_log_file,
    )

    # Wait for MCP to become reachable
    for i in range(15):
        await asyncio.sleep(1)
        if _is_looper_reachable():
            for _ in range(5):
                count = await discover_and_register(bridge, LOOPER_SSE_URL, prefix="looper")
                if count > 0:
                    break
                await asyncio.sleep(1)
            return (
                f"Looper engine (PID {_looper_engine_process.pid}) and "
                f"MCP server (PID {_looper_process.pid}) ready on port {LOOPER_MCP_PORT}. "
                f"{count} tools registered."
            )
        if _looper_process.poll() is not None:
            return f"Looper MCP process exited with code {_looper_process.returncode}. Check /tmp/looper-mcp.log."

    return (
        f"Looper engine (PID {_looper_engine_process.pid}) running. "
        f"MCP server (PID {_looper_process.pid}) not yet reachable. It may still be initializing."
    )


async def _stop_looper() -> str:
    """Stop the Looper MCP server and engine (internal helper)."""
    global _looper_process, _looper_log_file
    global _looper_engine_process, _looper_engine_log_file

    messages = []

    # Stop MCP server first
    if _looper_process is not None and _looper_process.poll() is None:
        unregister_all(bridge, prefix="looper")
        _looper_process.terminate()
        try:
            _looper_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _looper_process.kill()
            _looper_process.wait()
        messages.append(f"Looper MCP stopped (PID {_looper_process.pid}).")
        _looper_process = None
    else:
        _looper_process = None
        messages.append("No managed Looper MCP process to stop.")

    if _looper_log_file is not None:
        _looper_log_file.close()
        _looper_log_file = None

    # Then stop the engine
    if _looper_engine_process is not None and _looper_engine_process.poll() is None:
        _looper_engine_process.terminate()
        try:
            _looper_engine_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _looper_engine_process.kill()
            _looper_engine_process.wait()
        messages.append(f"Looper engine stopped (PID {_looper_engine_process.pid}).")
        _looper_engine_process = None
    else:
        _looper_engine_process = None
        messages.append("No managed Looper engine process to stop.")

    if _looper_engine_log_file is not None:
        _looper_engine_log_file.close()
        _looper_engine_log_file = None

    return " ".join(messages)


@bridge.tool()
async def looper_start() -> str:
    """Start the looper system (Looper MCP server + looperdooper)."""
    return await _start_looper()


@bridge.tool()
async def looper_stop() -> str:
    """Stop the looper system."""
    return await _stop_looper()


@bridge.tool()
async def looper_restart() -> str:
    """Restart the looper system (stop then start)."""
    stop_msg = await _stop_looper()
    await asyncio.sleep(1)
    start_msg = await _start_looper()
    return f"{stop_msg}\n{start_msg}"


@bridge.tool()
async def looper_status() -> str:
    """Check if the looper system is running and its MCP server is reachable."""
    process_running = _is_looper_running()
    reachable = _is_looper_reachable()

    if reachable:
        src = f"managed (PID {_looper_process.pid})" if process_running else "external"
        return f"Looper is running ({src}). MCP reachable at {LOOPER_SSE_URL}"
    elif process_running:
        return f"Looper process running (PID {_looper_process.pid}) but MCP not reachable yet."
    else:
        return "Looper is not running. Use looper_start to launch it."


@bridge.tool()
async def save_rig_session(name: str) -> str:
    """Save the full rig session (Carla + looper state + routing manifest)."""
    session_dir = RIG_SESSION_DIR / name
    session_dir.mkdir(parents=True, exist_ok=True)

    messages = []

    # Save Carla project if running
    carla_session = ""
    if _is_carla_reachable():
        carla_path = str(session_dir / "carla_project.carxp")
        try:
            async with sse_client(CARLA_SSE_URL) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    await session.call_tool("save_project", {"filename": carla_path})
            carla_session = carla_path
            messages.append(f"Carla session saved to {carla_path}")
        except Exception as e:
            messages.append(f"Failed to save Carla session: {e}")

    # Save looper session if running
    looper_session = ""
    if _is_looper_reachable():
        looper_path = str(session_dir / "looper_session.json")
        try:
            async with sse_client(LOOPER_SSE_URL) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    await session.call_tool("save_session", {"path": looper_path})
            looper_session = looper_path
            messages.append(f"Looper session saved to {looper_path}")
        except Exception as e:
            messages.append(f"Failed to save looper session: {e}")

    # Save rig manifest
    manifest = _build_rig_manifest(
        carla_running=_is_carla_reachable(),
        looper_running=_is_looper_reachable(),
        carla_session=carla_session,
        looper_session=looper_session,
    )
    manifest_path = session_dir / "rig_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    messages.append(f"Rig manifest saved to {manifest_path}")

    return "\n".join(messages)


@bridge.tool()
async def load_rig_session(name: str) -> str:
    """Load a saved rig session (starts backends if needed, restores state)."""
    session_dir = RIG_SESSION_DIR / name
    manifest_path = session_dir / "rig_manifest.json"

    if not manifest_path.exists():
        return f"No rig session found at {session_dir}"

    manifest = json.loads(manifest_path.read_text())
    messages = []

    carla_cfg = manifest.get("backends", {}).get("carla", {})
    if carla_cfg.get("session"):
        if not _is_carla_reachable():
            messages.append(await _start_carla())
        try:
            async with sse_client(CARLA_SSE_URL) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    await session.call_tool(
                        "load_project", {"filename": carla_cfg["session"]}
                    )
            messages.append("Carla session loaded.")
        except Exception as e:
            messages.append(f"Failed to load Carla session: {e}")

    looper_cfg = manifest.get("backends", {}).get("looper", {})
    if looper_cfg.get("session"):
        if not _is_looper_reachable():
            messages.append(await _start_looper())
        try:
            async with sse_client(LOOPER_SSE_URL) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    await session.call_tool(
                        "load_session", {"path": looper_cfg["session"]}
                    )
            messages.append("Looper session loaded.")
        except Exception as e:
            messages.append(f"Failed to load looper session: {e}")

    # Restore external Carla wiring (loopers handles its own JACK connections)
    from carla_mcp.utils.pw_link import (
        ensure_carla_to_monitors, find_capture_input_ports, pw_link_connect,
    )

    monitors_result = ensure_carla_to_monitors()
    captures = find_capture_input_ports()
    capture_connected = 0
    for i, cap in enumerate(captures[:2]):
        r = pw_link_connect(cap, f"Carla:audio-in{i + 1}")
        if r.success:
            capture_connected += 1

    mon_total = monitors_result["connected"] + monitors_result["already_connected"]
    messages.append(
        f"[Routing] Monitors: {mon_total}/2, Captures: {capture_connected}/{len(captures[:2])}"
    )

    return "\n".join(messages) if messages else "Nothing to load."


@bridge.tool()
async def list_rig_sessions() -> str:
    """List all saved rig sessions."""
    if not RIG_SESSION_DIR.exists():
        return "No rig sessions saved yet."
    sessions = sorted(d.name for d in RIG_SESSION_DIR.iterdir() if d.is_dir())
    if not sessions:
        return "No rig sessions saved yet."
    return "Saved rig sessions:\n" + "\n".join(f"  - {s}" for s in sessions)


@bridge.tool()
async def get_rig_status() -> str:
    """Get the status of all rig backends (Carla and looper)."""
    carla_msg = await carla_status()
    looper_msg = await looper_status()
    return f"=== Carla ===\n{carla_msg}\n\n=== Looper ===\n{looper_msg}"


async def _start_rig() -> str:
    """Start the full rig (internal helper)."""
    messages = []

    # Step 1: Start Carla (bridge engine + carla-control viewer)
    carla_msg = await _start_carla()
    messages.append(f"[Carla] {carla_msg}")

    # Step 2: Start Looper (engine + MCP server)
    looper_msg = await _start_looper()
    messages.append(f"[Looper] {looper_msg}")

    # Step 3: Create external pw-link connections using auto-discovery
    from carla_mcp.utils.pw_link import (
        pw_link_connect, pw_link_verify,
        find_monitor_output_ports, find_capture_input_ports,
    )

    captures = find_capture_input_ports()
    monitors = find_monitor_output_ports()

    external_connections = []
    # Captures -> Carla (live monitor)
    for i, cap in enumerate(captures[:2]):
        external_connections.append((cap, f"Carla:audio-in{i + 1}"))
    # Carla -> Monitors
    for i, mon in enumerate(monitors[:2]):
        external_connections.append((f"Carla:audio-out{i + 1}", mon))

    if not captures:
        messages.append("[Connections] WARNING: No capture input ports discovered")
    if not monitors:
        messages.append("[Connections] WARNING: No monitor output ports discovered")

    conn_results = []
    for src, dst in external_connections:
        result = pw_link_connect(src, dst)
        status = "OK" if result.success else f"FAIL: {result.message}"
        conn_results.append(f"  {src} -> {dst}: {status}")
    messages.append("[Connections]\n" + "\n".join(conn_results))

    # Step 4: Verify connections
    verified = sum(1 for src, dst in external_connections if pw_link_verify(src, dst))
    messages.append(f"[Verify] {verified}/{len(external_connections)} connections verified")

    return "\n\n".join(messages)


@bridge.tool()
async def start_rig() -> str:
    """Start the full rig: Carla engine, carla-control GUI, loopers engine, looper MCP, and audio connections."""
    return await _start_rig()


def _atexit_cleanup():
    """Ensure Carla and Looper are terminated on exit."""
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

    global _looper_process, _looper_log_file
    if _looper_process is not None and _looper_process.poll() is None:
        _looper_process.terminate()
        try:
            _looper_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _looper_process.kill()
            _looper_process.wait()
        _looper_process = None
    if _looper_log_file is not None:
        _looper_log_file.close()
        _looper_log_file = None

    global _looper_engine_process, _looper_engine_log_file
    if _looper_engine_process is not None and _looper_engine_process.poll() is None:
        _looper_engine_process.terminate()
        try:
            _looper_engine_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _looper_engine_process.kill()
            _looper_engine_process.wait()
        _looper_engine_process = None
    if _looper_engine_log_file is not None:
        _looper_engine_log_file.close()
        _looper_engine_log_file = None


atexit.register(_atexit_cleanup)


def main():
    bridge.run(transport="stdio")


if __name__ == "__main__":
    main()
