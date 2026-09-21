"""Bridge between Carla's single global engine callback and the worker cache.

This is the one piece of module-level state in the worker: Carla's C callback
is process-global, so the tap that feeds it into a PatchbayCache must be too.
"""

from __future__ import annotations

from typing import Optional

from carla_mcp.worker.patchbay import PatchbayCache

_cache: Optional[PatchbayCache] = None


def register(cache: Optional[PatchbayCache]) -> None:
    global _cache
    _cache = cache


def dispatch(action: int, plugin_id: int, value1: int, value2: int,
             value3: int, valuef: float, value_str: str) -> None:
    cache = _cache
    if cache is not None:
        cache.on_event(action, plugin_id, value1, value2, value3, valuef, value_str)
