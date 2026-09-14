import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anyio
import pytest

from carla_mcp.backends import legacy_sse
from carla_mcp.backends.rpc import RpcError


def _sse_ctx():
    @asynccontextmanager
    async def _ctx(url):
        yield (object(), object())
    return _ctx


class _FakeSession:
    def __init__(self, call_tool=None):
        self.initialize = AsyncMock()
        self.call_tool = call_tool or AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _client_session_factory(session):
    def _factory(read, write):
        return session
    return _factory


def _result(text, is_error=False):
    return SimpleNamespace(isError=is_error, content=[SimpleNamespace(text=text)])


def test_call_tool_success_parses_json():
    session = _FakeSession(call_tool=AsyncMock(return_value=_result('{"nodes": {}}')))
    with patch.object(legacy_sse, "sse_client", _sse_ctx()), \
         patch.object(legacy_sse, "ClientSession", _client_session_factory(session)):
        result = asyncio.run(legacy_sse.call_tool("http://x/sse", "rig_handles", {"a": 1}))
    assert result == {"nodes": {}}
    session.call_tool.assert_awaited_once_with("rig_handles", {"a": 1})
    session.initialize.assert_awaited_once()


def test_call_tool_raises_rpc_error_on_is_error_result():
    session = _FakeSession(call_tool=AsyncMock(return_value=_result("boom: node not found", is_error=True)))
    with patch.object(legacy_sse, "sse_client", _sse_ctx()), \
         patch.object(legacy_sse, "ClientSession", _client_session_factory(session)):
        with pytest.raises(RpcError) as exc:
            asyncio.run(legacy_sse.call_tool("http://x/sse", "remove_node", {"name": "n"}))
    assert exc.value.type == "internal"
    assert "remove_node" in exc.value.message
    assert "boom: node not found" in exc.value.message


def test_call_tool_times_out(monkeypatch):
    monkeypatch.setattr(legacy_sse, "LEGACY_SSE_TIMEOUT_S", 0.05)

    async def _hang(*args, **kwargs):
        await anyio.sleep(1)

    session = _FakeSession(call_tool=AsyncMock(side_effect=_hang))
    with patch.object(legacy_sse, "sse_client", _sse_ctx()), \
         patch.object(legacy_sse, "ClientSession", _client_session_factory(session)):
        with pytest.raises(RpcError) as exc:
            asyncio.run(legacy_sse.call_tool("http://x/sse", "rig_handles", {}))
    assert exc.value.type == "backend_unavailable"
    assert "timed out" in exc.value.message


def test_call_tool_unwraps_exception_group():
    async def _boom_ctx(url):
        raise ExceptionGroup("unhandled errors in a TaskGroup", [ConnectionRefusedError("refused")])
        yield  # pragma: no cover — unreachable, keeps this an async generator

    with patch.object(legacy_sse, "sse_client", asynccontextmanager(_boom_ctx)):
        with pytest.raises(RpcError) as exc:
            asyncio.run(legacy_sse.call_tool("http://x/sse", "export_rig_state", {}))
    assert exc.value.type == "backend_unavailable"
    assert "refused" in exc.value.message


def test_call_tool_does_not_swallow_keyboard_interrupt_in_group():
    async def _boom_ctx(url):
        raise BaseExceptionGroup("fatal", [KeyboardInterrupt()])
        yield  # pragma: no cover — unreachable, keeps this an async generator

    with patch.object(legacy_sse, "sse_client", asynccontextmanager(_boom_ctx)):
        with pytest.raises(BaseExceptionGroup) as exc:
            asyncio.run(legacy_sse.call_tool("http://x/sse", "rig_handles", {}))
    assert any(isinstance(e, KeyboardInterrupt) for e in exc.value.exceptions)


def test_call_tool_honours_explicit_timeout_override(monkeypatch):
    monkeypatch.setattr(legacy_sse, "LEGACY_SSE_TIMEOUT_S", 5.0)

    async def _hang(*args, **kwargs):
        await anyio.sleep(1)

    session = _FakeSession(call_tool=AsyncMock(side_effect=_hang))
    with patch.object(legacy_sse, "sse_client", _sse_ctx()), \
         patch.object(legacy_sse, "ClientSession", _client_session_factory(session)):
        with pytest.raises(RpcError) as exc:
            asyncio.run(legacy_sse.call_tool("http://x/sse", "import_rig_state", {}, timeout=0.05))
    assert exc.value.type == "backend_unavailable"
    assert "timed out after 0s" in exc.value.message


def test_call_tool_default_timeout_used_when_not_given(monkeypatch):
    monkeypatch.setattr(legacy_sse, "LEGACY_SSE_TIMEOUT_S", 0.05)

    async def _hang(*args, **kwargs):
        await anyio.sleep(1)

    session = _FakeSession(call_tool=AsyncMock(side_effect=_hang))
    with patch.object(legacy_sse, "sse_client", _sse_ctx()), \
         patch.object(legacy_sse, "ClientSession", _client_session_factory(session)):
        with pytest.raises(RpcError) as exc:
            asyncio.run(legacy_sse.call_tool("http://x/sse", "rig_handles", {}))
    assert "timed out after 0s" in exc.value.message
