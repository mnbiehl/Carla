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
import time
from pathlib import Path

from fastmcp import FastMCP
from mcp.client.sse import sse_client
from mcp import ClientSession

from carla_mcp.tool_proxy import discover_and_register, unregister_all
from carla_mcp.orchestration.jack_router import JackRouter
from carla_mcp.rig.converge import (
    RigOps, do_load, do_routing_reset, do_save, do_stop, do_verify,
)
from carla_mcp.rig.graph import RigGraph
from carla_mcp.rig.observe import observe as rig_observe
from carla_mcp.rig.session import SessionError, read_session
from carla_mcp.utils.pw_link import (
    pw_link_connect, pw_link_disconnect, pw_link_list_inputs, pw_link_list_outputs,
)
from looper_mcp.looper_client import LooperClient

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


def _tool_result_json(result) -> dict | None:
    """Extract and JSON-parse the text payload of an MCP tool call result.

    Tools that return a dict are delivered as one or more TextContent parts
    holding JSON.  Returns the parsed object, or None if nothing parses.
    """
    parts = []
    for content in getattr(result, "content", None) or []:
        text = getattr(content, "text", None)
        if text is not None:
            parts.append(text)
    raw = "".join(parts).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


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

# Track the a2jmidid process (managed mode: the bridge owns a2j's lifecycle)
_a2j_process: subprocess.Popen | None = None
_a2j_log_file = None

# Desired graph of the last loaded/saved session (verify_rig's default target)
_current_graph: RigGraph | None = None

LOOPER_JSON_PORT = int(os.getenv("LOOPER_JSON_PORT", "8088"))


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


def _carla_status_message() -> str:
    """Get Carla status message (internal helper)."""
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
async def carla_status() -> str:
    """Check if Carla is running and its MCP server is reachable."""
    return _carla_status_message()


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

    # Step 1: Launch the loopers audio engine via pw-jack in managed mode:
    # the bridge/rig graph is the only writer of connections (no self-wiring,
    # no MIDI auto-connect, no a2jmidid autostart in the engine).
    _looper_engine_log_file = open("/tmp/looper-engine.log", "w")
    _looper_engine_process = subprocess.Popen(
        ["pw-jack", LOOPERS_PATH, "--managed"],
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


def _is_a2j_running() -> bool:
    """True if our managed a2jmidid is alive, or an external one is running."""
    global _a2j_process
    if _a2j_process is not None:
        if _a2j_process.poll() is None:
            return True
        _a2j_process = None
    try:
        return subprocess.run(
            ["pgrep", "-x", "a2jmidid"], capture_output=True, timeout=3
        ).returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _start_a2j() -> str | None:
    """Start a2jmidid (managed). Returns None on success, error string on failure."""
    global _a2j_process, _a2j_log_file
    if _is_a2j_running():
        return None
    try:
        _a2j_log_file = open("/tmp/a2jmidid.log", "w")
        _a2j_process = subprocess.Popen(
            ["a2jmidid", "-e"],
            stdout=_a2j_log_file,
            stderr=_a2j_log_file,
        )
    except FileNotFoundError:
        return "a2jmidid not installed"
    except Exception as e:  # noqa: BLE001 — report, don't raise into tool
        return f"failed to start a2jmidid: {e}"
    return None


def _stop_a2j() -> str | None:
    """Stop the managed a2jmidid. External instances are reported, not killed."""
    global _a2j_process, _a2j_log_file
    if _a2j_process is not None and _a2j_process.poll() is None:
        _a2j_process.terminate()
        try:
            _a2j_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _a2j_process.kill()
            _a2j_process.wait()
        _a2j_process = None
        if _a2j_log_file is not None:
            _a2j_log_file.close()
            _a2j_log_file = None
        return None
    _a2j_process = None
    if _is_a2j_running():
        return "a2jmidid running but not managed by the bridge; left alone"
    return None


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


def _looper_status_message() -> str:
    """Get looper status message (internal helper)."""
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
async def looper_status() -> str:
    """Check if the looper system is running and its MCP server is reachable."""
    return _looper_status_message()


async def _carla_call(tool: str, args: dict) -> dict | str | None:
    """One SSE round-trip to the main Carla MCP server; returns parsed JSON
    dict when the tool returned JSON, else the raw text, else None."""
    async with sse_client(CARLA_SSE_URL) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
    parsed = _tool_result_json(result)
    if parsed is not None:
        return parsed
    parts = [getattr(c, "text", "") or "" for c in getattr(result, "content", []) or []]
    return "".join(parts).strip() or None


def _unwrap_looper_state(reply: dict | None) -> dict | None:
    """The Rust remote nests GetState under a "state" key; do_save/observe read
    main_muted/loopers at the top level, so peel one "state" envelope."""
    if isinstance(reply, dict) and "state" in reply and isinstance(reply["state"], dict):
        return reply["state"]
    return reply


class BridgeOps(RigOps):
    """Production RigOps: pw-link + SSE-to-Carla + looper TCP + Popen probes."""

    def __init__(self) -> None:
        self._router = JackRouter()
        self._looper = LooperClient(port=LOOPER_JSON_PORT)

    # ----- observation -------------------------------------------------

    def _unit_probe(self, unit) -> bool:
        if unit.kind == "carla-main":
            return _is_carla_reachable()
        if unit.kind == "looper-mcp":
            return _is_looper_reachable()
        if unit.kind == "looper-engine":
            return any(p.startswith("loopers:") for p in pw_link_list_outputs())
        if unit.kind == "a2j":
            return _is_a2j_running()
        if unit.kind == "carla-child":
            client = f"CarlaChain_{unit.node}"
            return f"{client}:audio-in1" in pw_link_list_inputs()
        return False

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph is not None else []

        async def _get_state():
            try:
                return _unwrap_looper_state(await self._looper.get_state())
            except ConnectionError:
                return None

        async def _get_handles():
            if not _is_carla_reachable():
                return {}
            result = await _carla_call("rig_handles", {})
            if isinstance(result, dict):
                return result.get("nodes", {})
            return {}

        return await rig_observe(
            units,
            list_links=self._router.list_connections,
            list_outputs=pw_link_list_outputs,
            list_inputs=pw_link_list_inputs,
            unit_probe=self._unit_probe,
            looper_get_state=_get_state,
            carla_handles=_get_handles,
        )

    # ----- processes ----------------------------------------------------

    async def start_unit(self, unit):
        if unit.kind in ("looper-engine", "looper-mcp"):
            message = await _start_looper()
            return None if "exited" not in message else message
        if unit.kind == "carla-main":
            message = await _start_carla()
            return None if "exited" not in message else message
        if unit.kind == "a2j":
            return _start_a2j()
        if unit.kind == "carla-child":
            return None  # respawned by import_rig_state during converge
        return f"unknown unit kind: {unit.kind}"

    async def stop_unit(self, unit):
        if unit.kind == "carla-child":
            if not _is_carla_reachable():
                return None
            try:
                result = await _carla_call("remove_node", {"name": unit.node})
            except Exception as e:  # noqa: BLE001
                return f"remove_node failed: {e}"
            if isinstance(result, dict) and not result.get("success", True):
                return result.get("message", "remove_node failed")
            return None
        if unit.kind == "carla-main":
            await _stop_carla()
            return None
        if unit.kind in ("looper-mcp", "looper-engine"):
            await _stop_looper()
            return None
        if unit.kind == "a2j":
            return _stop_a2j()
        return f"unknown unit kind: {unit.kind}"

    # ----- connections ---------------------------------------------------

    def connect(self, src, dst):
        result = pw_link_connect(src, dst)
        return None if result.success else (result.message or "pw-link failed")

    def disconnect(self, src, dst):
        result = pw_link_disconnect(src, dst)
        return None if result.success else (result.message or "pw-link failed")

    def wait_ports(self, ports, timeout_s=15.0):
        deadline = time.monotonic() + timeout_s
        missing = list(ports)
        while missing and time.monotonic() < deadline:
            live = set(pw_link_list_outputs()) | set(pw_link_list_inputs())
            missing = [p for p in missing if p not in live]
            if missing:
                time.sleep(0.5)
        return missing

    # ----- Carla payload ---------------------------------------------------

    async def load_carla_project(self, path):
        try:
            await _carla_call("load_project", {"filename": path})
            return None
        except Exception as e:  # noqa: BLE001
            return str(e)

    async def save_carla_project(self, path):
        try:
            await _carla_call("save_project", {"filename": path})
            return None
        except Exception as e:  # noqa: BLE001
            return str(e)

    async def import_rig_state(self, state, chains_dir):
        try:
            result = await _carla_call(
                "import_rig_state", {"state": state, "chains_dir": chains_dir}
            )
            return result if isinstance(result, dict) else {"messages": []}
        except Exception as e:  # noqa: BLE001
            return {"messages": [f"import_rig_state failed: {e}"]}

    async def export_rig_state(self, chains_dir):
        if not _is_carla_reachable():
            return None
        try:
            result = await _carla_call("export_rig_state", {"chains_dir": chains_dir})
            return result if isinstance(result, dict) else None
        except Exception:  # noqa: BLE001
            return None

    # ----- looper payload -------------------------------------------------

    async def _looper_command(self, command) -> str | None:
        try:
            response = await self._looper.send_command(command)
        except ConnectionError as e:
            return str(e)
        if isinstance(response, dict) and "error" in response:
            return str(response["error"])
        return None

    async def load_looper_session(self, project_path):
        return await self._looper_command({"LoadSession": project_path})

    async def looper_save_session_at(self, dir_path):
        return await self._looper_command({"SaveSessionAt": dir_path})

    async def looper_get_state(self):
        try:
            return _unwrap_looper_state(await self._looper.get_state())
        except ConnectionError:
            return None

    async def set_looper_mutes(self, main_muted, all_muted):
        err = await self._looper_command({"SetMainOutputMute": main_muted})
        if err:
            return err
        return await self._looper_command({"SetAllOutputsMute": all_muted})


@bridge.tool()
async def save_rig_session(name: str) -> str:
    """Save the live rig as a v3 rig_session.json (self-verifying).

    Report opens with OK / DEGRADED: <n> issues / FAILED: <reason>.
    """
    global _current_graph
    session_dir = RIG_SESSION_DIR / name
    report = await do_save(name, session_dir, BridgeOps())
    try:
        _current_graph = read_session(session_dir).graph
    except SessionError:
        pass  # report already carries the FAILED verdict
    return report


@bridge.tool()
async def load_rig_session(name: str) -> str:
    """Load a rig session: read/migrate -> clean slate -> converge -> verify.

    Report opens with OK / DEGRADED: <n> issues / FAILED: <reason>.
    """
    global _current_graph
    session_dir = RIG_SESSION_DIR / name
    report = await do_load(name, session_dir, BridgeOps())
    if not report.startswith("FAILED"):
        try:
            _current_graph = read_session(session_dir).graph
        except SessionError:
            pass
    return report


@bridge.tool()
async def verify_rig(name: str = "") -> str:
    """Read-only: is the live rig still what the session says it should be?

    Verifies against the named session, or the last loaded/saved session
    when *name* is empty. Uses the exact same diff the load path uses.
    """
    if name:
        try:
            graph = read_session(RIG_SESSION_DIR / name).graph
        except SessionError as e:
            return f"FAILED: {e}"
    elif _current_graph is not None:
        graph = _current_graph
    else:
        return "FAILED: no rig session loaded this run; pass a session name"
    return await do_verify(graph, BridgeOps())


@bridge.tool()
async def rig_routing_reset() -> str:
    """Clean slate: disconnect every pw link touching rig port space
    (loopers:*, Carla*, and MIDI into the looper). Manual escape hatch
    for stale PipeWire link tangles."""
    return await do_routing_reset(BridgeOps())


@bridge.tool()
async def stop_rig(save_as: str = "") -> str:
    """Tear the rig down (children -> main Carla -> looper MCP -> looper
    engine -> a2j), verified dead. Optionally save first with *save_as*."""
    global _current_graph
    parts = []
    ops = BridgeOps()
    if save_as:
        parts.append(await do_save(save_as, RIG_SESSION_DIR / save_as, ops))
    parts.append(await do_stop(_current_graph, ops))
    _current_graph = None
    return "\n\n".join(parts)


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
    carla_msg = _carla_status_message()
    looper_msg = _looper_status_message()
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

    global _a2j_process, _a2j_log_file
    if _a2j_process is not None and _a2j_process.poll() is None:
        _a2j_process.terminate()
        try:
            _a2j_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _a2j_process.kill()
            _a2j_process.wait()
        _a2j_process = None
    if _a2j_log_file is not None:
        _a2j_log_file.close()
        _a2j_log_file = None


atexit.register(_atexit_cleanup)


def main():
    bridge.run(transport="stdio")


if __name__ == "__main__":
    main()
