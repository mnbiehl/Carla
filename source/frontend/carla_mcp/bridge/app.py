"""The Bridge object: all state the server needs, no module globals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from carla_mcp.backends.carla import CarlaClient
from carla_mcp.backends.looper import LooperClient
from carla_mcp.backends.processes import ProcessManager
from carla_mcp.backends.rpc import CarlaRpc, JsonLinesTransport
from carla_mcp.bridge.config import BridgeConfig
from carla_mcp.rig.graph import RigGraph

LegacySse = Callable[[str, str, dict], Awaitable[Any]]


@dataclass
class Bridge:
    config: BridgeConfig
    processes: ProcessManager
    carla: CarlaClient
    looper: LooperClient
    legacy_sse: LegacySse
    graph: Optional[RigGraph] = None
    version: str = "dev"
    session_name: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Bridge":
        from carla_mcp.backends.legacy_sse import call_tool
        cfg = BridgeConfig.from_env()
        return cls(
            config=cfg,
            processes=ProcessManager(cfg.log_dir),
            carla=CarlaClient(CarlaRpc(JsonLinesTransport("127.0.0.1", cfg.carla_rpc_port))),
            looper=LooperClient(JsonLinesTransport("127.0.0.1", cfg.looper_port)),
            legacy_sse=call_tool,
            version=_git_rev(cfg),
        )

    @classmethod
    def for_tests(cls, tmp_dir: Optional[str] = None, legacy_sse: Optional[LegacySse] = None,
                  env: Optional[dict] = None) -> "Bridge":
        import tempfile
        base = tmp_dir or tempfile.mkdtemp(prefix="carla-mcp-test-")
        cfg = BridgeConfig.from_env(env or {"HOME": base, "XDG_STATE_HOME": base})

        async def _no_sse(url, name, args):
            return None

        return cls(
            config=cfg,
            processes=ProcessManager(cfg.log_dir),
            carla=CarlaClient(CarlaRpc(JsonLinesTransport("127.0.0.1", cfg.carla_rpc_port))),
            looper=LooperClient(JsonLinesTransport("127.0.0.1", cfg.looper_port)),
            legacy_sse=legacy_sse or _no_sse,
            version="test",
        )


def _git_rev(cfg: BridgeConfig) -> str:
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(cfg.frontend_dir),
                             capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
