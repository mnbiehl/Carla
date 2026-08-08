### Task 14: Bridge integration — managed looper, a2j lifecycle, `BridgeOps`, new MCP tools

**Files:**
- Modify: `source/frontend/carla_mcp/mcp_stdio_bridge.py`:
  - `_start_looper` (lines 275–353): launch with `--managed`
  - delete `_build_rig_manifest` (lines 58–75)
  - replace `save_rig_session` (lines 444–530) and `load_rig_session` (lines 533–634) bodies with thin wrappers
  - add a2j globals + `_start_a2j`/`_stop_a2j`, `BridgeOps`, `_current_graph` global, and tools `verify_rig`, `rig_routing_reset`, `stop_rig` (insert after `get_rig_status`, line ~654); leave `start_rig` (656–707) untouched (legacy, out of scope)
- Delete: `source/frontend/carla_mcp/tests/test_load_rig_routing.py`, `source/frontend/carla_mcp/tests/test_rig_routing_roundtrip.py` (both test the removed v2 imperative path; intent restored by Task 15's round-trip test)
- Modify: `source/frontend/carla_mcp/tests/test_rig_session.py` — delete the two `_build_rig_manifest` tests; keep the file only if other tests remain, else delete it
- Create: `source/frontend/carla_mcp/tests/test_bridge_rig_tools.py`

**Interfaces:**
- Consumes: `do_load`, `do_save`, `do_verify`, `do_routing_reset`, `do_stop` (Tasks 8–11), `observe` (Task 12), `LooperClient` (`looper_mcp.looper_client`, TCP 8088), `JackRouter`, `utils/pw_link` list functions.
- Produces `BridgeOps(RigOps)` with:
  - `observe(graph)` — `JackRouter().list_connections()`, `pw_link_list_outputs/inputs`, unit probes (`carla:main` → `_is_carla_reachable()`; `carla-child` → `f"{jack_client}:audio-in1"` in live inputs where `jack_client = f"CarlaChain_{unit.node}"`; `looper:engine` → any live port starting `loopers:`; `looper:mcp` → `_is_looper_reachable()`; `a2j` → managed Popen alive or `pgrep -x a2jmidid` rc 0), `looper_get_state` via `LooperClient.get_state()` (None on `ConnectionError`), `carla_handles` via SSE `rig_handles` call parsed with `_tool_result_json`
  - `start_unit`: `looper-engine`/`looper-mcp` → `await _start_looper()`; `carla-main` → `await _start_carla()`; `a2j` → `_start_a2j()`; `carla-child` → return `None` with no-op (respawned by `import_rig_state`)
  - `stop_unit`: `carla-child` → SSE `remove_node(unit.node)` on main Carla; `carla-main` → `await _stop_carla()`; `looper-mcp`+`looper-engine` → `await _stop_looper()` (idempotent, second call reports nothing to stop); `a2j` → `_stop_a2j()`
  - `connect`/`disconnect` → `pw_link_connect`/`pw_link_disconnect`, returning `result.message or "pw-link failed"` on failure else None
  - `wait_ports` → poll `set(pw_link_list_outputs()) | set(pw_link_list_inputs())` every 0.5 s until timeout, return still-missing
  - `load_carla_project`/`save_carla_project`/`import_rig_state`/`export_rig_state` → SSE calls to `CARLA_SSE_URL` (`load_project`, `save_project`, `import_rig_state`, `export_rig_state`) using the existing `sse_client`/`ClientSession` pattern and `_tool_result_json`
  - `load_looper_session` → `LooperClient.send_command({"LoadSession": path})`; `looper_save_session_at` → `{"SaveSessionAt": dir}`; `set_looper_mutes` → `{"SetMainOutputMute": m}` then `{"SetAllOutputsMute": a}`; error dicts (`{"error": ...}`) returned as strings
- New/changed MCP tools (all return a verdict-first report string):
```python
@bridge.tool() async def save_rig_session(name: str) -> str      # do_save; updates _current_graph
@bridge.tool() async def load_rig_session(name: str) -> str      # do_load; updates _current_graph
@bridge.tool() async def verify_rig(name: str = "") -> str       # named session or _current_graph; FAILED if neither
@bridge.tool() async def rig_routing_reset() -> str              # do_routing_reset
@bridge.tool() async def stop_rig(save_as: str = "") -> str      # optional do_save first, then do_stop
```
- `_start_looper` engine spawn becomes `["pw-jack", LOOPERS_PATH, "--managed"]`; `_atexit_cleanup` also terminates `_a2j_process`.

**Steps:**

- [ ] Write failing test `tests/test_bridge_rig_tools.py`:

```python
"""Tests for the bridge's thin rig tools and managed-mode process handling."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import carla_mcp.mcp_stdio_bridge as bridge_mod


class TestManagedLooperLaunch:
    @patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
    @patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", return_value=False)
    def test_engine_launched_with_managed_flag(self, _reach, mock_popen):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 1234
        mock_popen.return_value = proc
        with patch("carla_mcp.mcp_stdio_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="loopers:loop0_out_l", returncode=0)
            with patch("carla_mcp.mcp_stdio_bridge._is_looper_running", return_value=False):
                # stop before MCP phase by making reachability stay false and
                # patching discover to no-op; we only care about the engine argv
                asyncio.run(bridge_mod._start_looper())
        argv = mock_popen.call_args_list[0].args[0]
        assert argv[0] == "pw-jack"
        assert argv[-1] == "--managed"


class TestThinTools:
    def test_load_delegates_to_do_load(self, tmp_path):
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            with patch("carla_mcp.mcp_stdio_bridge.do_load",
                       new=AsyncMock(return_value="OK")) as mock_load:
                result = asyncio.run(bridge_mod.load_rig_session.fn("mysession"))
        assert result == "OK"
        name, session_dir = mock_load.await_args.args[0], mock_load.await_args.args[1]
        assert name == "mysession"
        assert session_dir == tmp_path / "mysession"

    def test_save_delegates_to_do_save(self, tmp_path):
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            with patch("carla_mcp.mcp_stdio_bridge.do_save",
                       new=AsyncMock(return_value="OK")) as mock_save:
                result = asyncio.run(bridge_mod.save_rig_session.fn("mysession"))
        assert result == "OK"
        assert mock_save.await_args.args[0] == "mysession"

    def test_verify_without_session_is_failed(self):
        bridge_mod._current_graph = None
        result = asyncio.run(bridge_mod.verify_rig.fn(""))
        assert result.startswith("FAILED:")

    def test_verify_with_named_session_reads_it(self, tmp_path):
        import json
        sdir = tmp_path / "named"
        sdir.mkdir()
        (sdir / "rig_session.json").write_text(json.dumps(
            {"version": 3, "name": "named", "nodes": [], "edges": [],
             "runtime_units": []}))
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            with patch("carla_mcp.mcp_stdio_bridge.do_verify",
                       new=AsyncMock(return_value="OK")) as mock_verify:
                result = asyncio.run(bridge_mod.verify_rig.fn("named"))
        assert result == "OK"
        mock_verify.assert_awaited_once()

    def test_routing_reset_delegates(self):
        with patch("carla_mcp.mcp_stdio_bridge.do_routing_reset",
                   new=AsyncMock(return_value="OK")) as mock_reset:
            result = asyncio.run(bridge_mod.rig_routing_reset.fn())
        assert result == "OK"
        mock_reset.assert_awaited_once()

    def test_stop_rig_saves_first_when_asked(self, tmp_path):
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            with patch("carla_mcp.mcp_stdio_bridge.do_save",
                       new=AsyncMock(return_value="OK")) as mock_save:
                with patch("carla_mcp.mcp_stdio_bridge.do_stop",
                           new=AsyncMock(return_value="OK")) as mock_stop:
                    result = asyncio.run(bridge_mod.stop_rig.fn("keepsake"))
        mock_save.assert_awaited_once()
        mock_stop.assert_awaited_once()
        assert result.count("OK") >= 1

    def test_stop_rig_without_save(self):
        with patch("carla_mcp.mcp_stdio_bridge.do_stop",
                   new=AsyncMock(return_value="OK")) as mock_stop:
            result = asyncio.run(bridge_mod.stop_rig.fn(""))
        mock_stop.assert_awaited_once()
        assert result == "OK"

    def test_legacy_manifest_builder_is_gone(self):
        assert not hasattr(bridge_mod, "_build_rig_manifest")


class TestBridgeOpsPrimitives:
    def test_connect_returns_none_on_success(self):
        from carla_mcp.utils.pw_link import PwLinkResult
        ops = bridge_mod.BridgeOps()
        with patch("carla_mcp.mcp_stdio_bridge.pw_link_connect",
                   return_value=PwLinkResult(success=True)):
            assert ops.connect("a:1", "b:1") is None

    def test_connect_returns_message_on_failure(self):
        from carla_mcp.utils.pw_link import PwLinkResult
        ops = bridge_mod.BridgeOps()
        with patch("carla_mcp.mcp_stdio_bridge.pw_link_connect",
                   return_value=PwLinkResult(success=False, message="nope")):
            assert ops.connect("a:1", "b:1") == "nope"

    def test_wait_ports_returns_missing_after_timeout(self):
        ops = bridge_mod.BridgeOps()
        with patch("carla_mcp.mcp_stdio_bridge.pw_link_list_outputs",
                   return_value=["have:1"]):
            with patch("carla_mcp.mcp_stdio_bridge.pw_link_list_inputs",
                       return_value=[]):
                missing = ops.wait_ports(["have:1", "want:1"], timeout_s=0.1)
        assert missing == ["want:1"]
```

- [ ] Run and see it fail: `uv run pytest source/frontend/carla_mcp/tests/test_bridge_rig_tools.py -v` — expect `AttributeError: module 'carla_mcp.mcp_stdio_bridge' has no attribute 'BridgeOps'` (plus missing `do_load`/`verify_rig` names).
- [ ] Implement in `mcp_stdio_bridge.py`. Add imports near the top (after existing imports, line ~40):

```python
import time

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
```

Delete `_build_rig_manifest` (lines 58–75). Add globals after `_looper_engine_log_file` (line ~113):

```python
# Track the a2jmidid process (managed mode: the bridge owns a2j's lifecycle)
_a2j_process: subprocess.Popen | None = None
_a2j_log_file = None

# Desired graph of the last loaded/saved session (verify_rig's default target)
_current_graph: RigGraph | None = None

LOOPER_JSON_PORT = int(os.getenv("LOOPER_JSON_PORT", "8088"))
```

In `_start_looper` (line ~290) change the engine spawn to managed mode:

```python
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
```

Add a2j helpers (after `_stop_looper`, line ~400):

```python
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
```

Add `BridgeOps` and the tools (replace `save_rig_session` lines 444–530 and `load_rig_session` lines 533–634; insert `BridgeOps` before them):

```python
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
                return await self._looper.get_state()
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
            return await self._looper.get_state()
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
```

Extend `_atexit_cleanup` (line ~710) with an a2j block mirroring the looper-engine block:

```python
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
```

- [ ] Delete the superseded tests of the removed imperative path:
```
git rm source/frontend/carla_mcp/tests/test_load_rig_routing.py source/frontend/carla_mcp/tests/test_rig_routing_roundtrip.py source/frontend/carla_mcp/tests/test_rig_session.py
```
(`test_rig_session.py` contains only `_build_rig_manifest` tests — verified; its v3 successor is `test_rig_session_v3.py`.)
- [ ] Run pass: `uv run pytest source/frontend/carla_mcp/tests/test_bridge_rig_tools.py source/frontend/carla_mcp/tests/test_start_rig.py source/frontend/carla_mcp/tests/test_bridge_looper_lifecycle.py -v` (fix `test_bridge_looper_lifecycle.py` expectations if it asserts the exact engine argv — it must now expect the trailing `--managed`).
- [ ] Full suite: `uv run pytest` — everything green.
- [ ] Commit:
```
git add -A source/frontend/carla_mcp/mcp_stdio_bridge.py source/frontend/carla_mcp/tests/
git commit -m "feat(bridge): reconciler-backed rig tools, managed looper, a2j lifecycle

Replaces the imperative v2 save/load path with thin wrappers over the rig
converge engine; adds verify_rig, rig_routing_reset, stop_rig; launches
loopers with --managed; bridge owns a2jmidid.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

