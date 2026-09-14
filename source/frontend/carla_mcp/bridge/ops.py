"""Production RigOps over the Bridge: pw-link + worker RPC + looper TCP + processes."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import List, Optional, Sequence

from carla_mcp.backends import pw_link
from carla_mcp.backends.legacy_sse import LEGACY_SSE_LONG_TIMEOUT_S
from carla_mcp.backends.looper import LONG_OP_TIMEOUT_S
from carla_mcp.backends.processes import a2j_running, ports_present, tcp_reachable
from carla_mcp.backends.rpc import RpcError
from carla_mcp.bridge.app import Bridge
from carla_mcp.rig.converge import RigOps
from carla_mcp.rig.graph import RigGraph, RuntimeUnit
from carla_mcp.rig.observe import ObservedState, observe as rig_observe

# loopers' SaveSessionAt replies "ok" as soon as the command is enqueued, well
# before the (potentially 100+ MB) audio and project.loopers file are written
# (loopers-engine/src/session.rs). looper_save_session_at below polls for the
# project file to actually land instead of trusting the ack.
LOOPER_PROJECT_FILE = "project.loopers"
LOOPER_SAVE_POLL_S = 0.25
LOOPER_SAVE_WAIT_S = LONG_OP_TIMEOUT_S
LOOPER_SAVE_CLOCK_SLACK_MS = 2000


def _read_looper_save_time_ms(project_path: Path) -> Optional[int]:
    """Return project.loopers' save_time if the file is a complete, valid
    JSON document with an integer save_time; None otherwise (missing file,
    partial write, or a save_time we can't trust)."""
    try:
        raw = project_path.read_text()
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    save_time = data.get("save_time")
    if isinstance(save_time, bool) or not isinstance(save_time, int):
        return None
    return save_time


class BridgeOps(RigOps):
    def __init__(self, bridge: Bridge):
        self.b = bridge
        # Instance attributes (not module-level state) so tests can inject
        # fast timings without monkeypatching module constants.
        self._looper_save_poll_s = LOOPER_SAVE_POLL_S
        self._looper_save_wait_s = LOOPER_SAVE_WAIT_S

    # ----- observation -------------------------------------------------

    def carla_up(self) -> bool:
        return tcp_reachable("127.0.0.1", self.b.config.carla_rpc_port)

    def looper_up(self) -> bool:
        return tcp_reachable("127.0.0.1", self.b.config.looper_port)

    def unit_probe(self, unit: RuntimeUnit) -> bool:
        if unit.kind == "carla-main":
            return self.carla_up()
        if unit.kind == "looper-engine":
            return ports_present("loopers:", pw_link.list_outputs)
        if unit.kind == "looper-mcp":
            return self.looper_up()
        if unit.kind == "a2j":
            return a2j_running()
        if unit.kind == "carla-child":
            return f"CarlaChain_{unit.node}:audio-in1" in pw_link.list_inputs()
        return False

    async def observe(self, graph: Optional[RigGraph]) -> ObservedState:
        units = list(graph.runtime_units.values()) if graph is not None else []

        async def _state():
            try:
                return await self.b.looper.get_state()
            except RpcError:
                return None

        async def _handles():
            if not self.carla_up():
                return {}
            try:
                result = await self.b.legacy_sse(self.b.config.carla_sse_url, "rig_handles", {})
            except RpcError:
                return {}
            return result.get("nodes", {}) if isinstance(result, dict) else {}

        return await rig_observe(
            units,
            list_links=pw_link.list_links,
            list_outputs=pw_link.list_outputs,
            list_inputs=pw_link.list_inputs,
            unit_probe=self.unit_probe,
            looper_get_state=_state,
            carla_handles=_handles,
        )

    # ----- processes ----------------------------------------------------

    async def start_unit(self, unit: RuntimeUnit) -> Optional[str]:
        from carla_mcp.bridge import units
        if unit.kind == "carla-main":
            return await units.start_carla_main(self.b)
        if unit.kind == "looper-engine":
            return await units.start_looper_engine(self.b)
        if unit.kind == "a2j":
            return units.start_a2j(self.b)
        if unit.kind in ("looper-mcp", "carla-child"):
            return None
        return f"unknown unit kind: {unit.kind}"

    async def stop_unit(self, unit: RuntimeUnit) -> Optional[str]:
        from carla_mcp.bridge import units
        if unit.kind == "carla-child":
            if not self.carla_up():
                return f"cannot remove {unit.node}: carla not reachable"
            try:
                result = await self.b.legacy_sse(self.b.config.carla_sse_url, "remove_node", {"name": unit.node})
            except RpcError as exc:
                return f"remove_node failed: {exc.message}"
            if isinstance(result, dict) and not result.get("success", True):
                return str(result.get("message", "remove_node failed"))
            return None
        if unit.kind == "carla-main":
            return await units.stop_carla_main(self.b)
        if unit.kind == "looper-engine":
            return await units.stop_looper_engine(self.b)
        if unit.kind == "a2j":
            return units.stop_a2j(self.b)
        if unit.kind == "looper-mcp":
            return None
        return f"unknown unit kind: {unit.kind}"

    # ----- connections ---------------------------------------------------

    def connect(self, src: str, dst: str) -> Optional[str]:
        return pw_link.connect(src, dst)

    def disconnect(self, src: str, dst: str) -> Optional[str]:
        return pw_link.disconnect(src, dst)

    def wait_ports(self, ports: Sequence[str], timeout_s: float = 15.0) -> List[str]:
        deadline = time.monotonic() + timeout_s
        missing = list(ports)
        while missing and time.monotonic() < deadline:
            live = set(pw_link.list_outputs()) | set(pw_link.list_inputs())
            missing = [p for p in missing if p not in live]
            if missing:
                time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
        return missing

    # ----- Carla payload ---------------------------------------------------

    async def load_carla_project(self, path: str) -> Optional[str]:
        try:
            await self.b.carla.project_load(path=path)
        except RpcError as exc:
            return exc.message
        return None

    async def save_carla_project(self, path: str) -> Optional[str]:
        try:
            await self.b.carla.project_save(path=path)
        except RpcError as exc:
            return exc.message
        return None

    async def import_rig_state(self, state: dict, chains_dir: str) -> dict:
        try:
            result = await self.b.legacy_sse(self.b.config.carla_sse_url, "import_rig_state",
                                             {"state": state, "chains_dir": chains_dir},
                                             timeout=LEGACY_SSE_LONG_TIMEOUT_S)
        except RpcError as exc:
            return {"messages": [f"import_rig_state failed: {exc.message}"]}
        return result if isinstance(result, dict) else {"messages": []}

    async def export_rig_state(self, chains_dir: str) -> Optional[dict]:
        if not self.carla_up():
            return None
        try:
            result = await self.b.legacy_sse(self.b.config.carla_sse_url, "export_rig_state",
                                             {"chains_dir": chains_dir},
                                             timeout=LEGACY_SSE_LONG_TIMEOUT_S)
        except RpcError as exc:
            # Distinct from "carla not reachable": the port answered, the
            # tool call itself failed (timeout, isError). No "nodes" key,
            # so do_save reports the real reason instead of misreporting
            # this as carla being down.
            return {"error": f"export_rig_state failed: {exc.message}"}
        return result if isinstance(result, dict) else None

    # ----- looper payload -------------------------------------------------

    async def load_looper_session(self, project_path: str) -> Optional[str]:
        try:
            await self.b.looper.load_session(project_path)
        except RpcError as exc:
            return exc.message
        return None

    async def looper_save_session_at(self, dir_path: str) -> Optional[str]:
        request_ms = int(time.time() * 1000)
        try:
            await self.b.looper.save_session_at(dir_path)
        except RpcError as exc:
            return exc.message

        # The ack above only means the save was enqueued (remote.rs replies
        # before any work happens). Poll for the project file actually
        # landing with a fresh save_time before trusting the save is done.
        project_path = Path(dir_path) / LOOPER_PROJECT_FILE
        poll_s = self._looper_save_poll_s
        wait_s = self._looper_save_wait_s
        deadline = time.monotonic() + wait_s
        while True:
            save_time = _read_looper_save_time_ms(project_path)
            if save_time is not None and save_time >= request_ms - LOOPER_SAVE_CLOCK_SLACK_MS:
                return None
            if time.monotonic() >= deadline:
                return (f"looper save did not complete within {int(wait_s)}s "
                        f"({dir_path}/{LOOPER_PROJECT_FILE})")
            await asyncio.sleep(poll_s)

    async def looper_get_state(self) -> Optional[dict]:
        try:
            return await self.b.looper.get_state()
        except RpcError:
            return None

    async def set_looper_mutes(self, main_muted: bool, all_muted: bool) -> Optional[str]:
        try:
            await self.b.looper.set_main_mute(main_muted)
            await self.b.looper.set_all_mute(all_muted)
        except RpcError as exc:
            return exc.message
        return None
