"""Static tool registration. Every tool exists whether or not its backend is up."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from mcp.types import ToolAnnotations

from carla_mcp.bridge.app import Bridge


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
