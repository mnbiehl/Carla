"""Bridge configuration — the only module that reads environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

_FRONTEND_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_LOOPERS = _FRONTEND_DIR.parents[2] / "looperdooper" / "target" / "release" / "loopers"


@dataclass(frozen=True)
class BridgeConfig:
    carla_python: str
    loopers_path: str
    looper_port: int
    carla_rpc_port: int
    session_dir: Path
    log_dir: Path
    frontend_dir: Path
    carla_sse_url: str
    autosave_before_destructive: bool

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "BridgeConfig":
        e = os.environ if env is None else env
        home = Path(e.get("HOME", str(Path.home())))
        state_home = Path(e.get("XDG_STATE_HOME", str(home / ".local" / "state")))
        sse_host = e.get("CARLA_MCP_HOST", "127.0.0.1")
        sse_port = e.get("CARLA_MCP_PORT", "3001")
        return cls(
            carla_python=e.get("CARLA_PYTHON_PATH", "/usr/bin/python3"),
            loopers_path=e.get("LOOPERS_PATH", str(_DEFAULT_LOOPERS)),
            looper_port=int(e.get("LOOPER_JSON_PORT", "8088")),
            carla_rpc_port=int(e.get("CARLA_RPC_PORT", "8089")),
            session_dir=Path(e.get("RIG_SESSION_DIR", str(home / ".config" / "rig-sessions"))),
            log_dir=state_home / "carla-mcp",
            frontend_dir=_FRONTEND_DIR,
            carla_sse_url=f"http://{sse_host}:{sse_port}/sse",
            autosave_before_destructive=e.get("CARLA_MCP_AUTOSAVE_BEFORE_DESTRUCTIVE", "0") == "1",
        )
