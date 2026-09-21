"""The one reply shape for every tool, and the boundary that enforces it.

Tools raise ToolError (or let RpcError propagate); they never catch broad
exceptions themselves.  tool_boundary is one of the three allowed
`except Exception` sites.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Iterable, List

from carla_mcp.backends.rpc import RpcError

log = logging.getLogger("carla_mcp.bridge")

ERROR_TYPES = ("not_found", "validation", "backend_unavailable", "degraded", "internal")


class ToolError(Exception):
    def __init__(self, type: str, message: str, notes: Iterable[str] = ()):
        super().__init__(f"{type}: {message}")
        self.type = type if type in ERROR_TYPES else "internal"
        self.message = message
        self.notes: List[str] = list(notes)


def ok(result: Any, notes: Iterable[str] = ()) -> dict:
    return {"ok": True, "result": result, "error": None, "notes": list(notes)}


def fail(type: str, message: str, notes: Iterable[str] = ()) -> dict:
    return {"ok": False, "result": None, "error": {"type": type, "message": message},
            "notes": list(notes)}


def _is_reply(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"ok", "result", "error", "notes"}


def tool_boundary(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            value = await fn(*args, **kwargs)
        except ToolError as exc:
            return fail(exc.type, exc.message, exc.notes)
        except RpcError as exc:
            return fail(exc.type, exc.message)
        except Exception as exc:  # noqa: BLE001 — tool boundary
            log.exception("tool %s failed", fn.__name__)
            return fail("internal", f"{type(exc).__name__}: {exc}")
        return value if _is_reply(value) else ok(value)
    return wrapper
