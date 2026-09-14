"""Typed client for the loopers engine's JSON remote (port 8088).

Levels are dB (engine schema v2).  Loopers are addressed by engine id; the
positional port index comes back in GetState and is what the rig graph uses
for loopN_* port names.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional

from carla_mcp.backends.rpc import JsonLinesTransport, RpcError

_LOOPER_FIELDS = ("id", "name", "port_index", "mode", "level_db", "pan", "input_source")

LONG_OP_TIMEOUT_S = 120.0


class LooperClient:
    def __init__(self, transport: JsonLinesTransport):
        self.transport = transport

    async def reachable(self) -> bool:
        return await self.transport.reachable()

    async def command(self, cmd: Any, timeout: Optional[float] = None) -> dict:
        reply = await self.transport.request(json.dumps(cmd), timeout=timeout)
        if "error" in reply:
            raise RpcError("internal", str(reply["error"]))
        return reply

    @staticmethod
    def target_by_id(looper_id: int) -> dict:
        return {"Id": int(looper_id)}

    async def _looper_cmd(self, looper_id: int, cmd: Any) -> dict:
        return await self.command({"Looper": [cmd, self.target_by_id(looper_id)]})

    # ----- state ---------------------------------------------------------

    async def get_state(self) -> dict:
        reply = await self.command("GetState")
        state = reply.get("state")
        if not isinstance(state, dict):
            raise RpcError("internal", "GetState reply missing 'state' envelope")
        return state

    async def loopers(self) -> List[dict]:
        state = await self.get_state()
        rows = []
        for entry in state.get("loopers", []) or []:
            if entry.get("port_index") is None:
                continue
            rows.append({k: entry.get(k) for k in _LOOPER_FIELDS})
        rows.sort(key=lambda r: r["port_index"])
        return rows

    # ----- sessions ------------------------------------------------------

    async def load_session(self, project_path: str) -> dict:
        return await self.command({"LoadSession": project_path}, timeout=LONG_OP_TIMEOUT_S)

    async def save_session_at(self, dir_path: str) -> dict:
        return await self.command({"SaveSessionAt": dir_path}, timeout=LONG_OP_TIMEOUT_S)

    # ----- mix -----------------------------------------------------------

    async def set_main_mute(self, muted: bool) -> dict:
        return await self.command({"SetMainOutputMute": bool(muted)})

    async def set_all_mute(self, muted: bool) -> dict:
        return await self.command({"SetAllOutputsMute": bool(muted)})

    async def set_level_db(self, looper_id: int, level_db: float) -> dict:
        return await self._looper_cmd(looper_id, {"SetLevel": float(level_db)})

    async def set_pan(self, looper_id: int, pan: float) -> dict:
        return await self._looper_cmd(looper_id, {"SetPan": float(pan)})
