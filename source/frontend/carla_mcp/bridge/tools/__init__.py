"""Static tool registration. Every tool exists whether or not its backend is up."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List

from mcp.types import ToolAnnotations

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.result import ToolError

BUSY_MESSAGE = "another rig operation is in progress; try again when it finishes"


@asynccontextmanager
async def exclusive(b: Bridge) -> AsyncIterator[None]:
    """Hold the bridge's rig-operation lock; fail fast (validation) if another
    mutating tool holds it. The check and the uncontended acquire run without
    an intervening await, so they are atomic on the event loop."""
    if b.lock.locked():
        raise ToolError("validation", BUSY_MESSAGE)
    async with b.lock:
        yield


@dataclass
class ToolSpec:
    name: str
    fn: Callable[..., Any]
    annotations: Dict[str, bool] = field(default_factory=dict)


def register_all(mcp, bridge: Bridge) -> List[ToolSpec]:
    from carla_mcp.bridge.tools import lifecycle, sessions
    specs: List[ToolSpec] = []
    for module in (lifecycle, sessions):
        specs.extend(module.build(bridge))
    for spec in specs:
        mcp.tool(spec.fn, name=spec.name,
                 annotations=ToolAnnotations(**spec.annotations) if spec.annotations else None)
    return specs
