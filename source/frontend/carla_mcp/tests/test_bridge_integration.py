"""Integration test: bridge discovers tools from two mock backends with prefixes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastmcp import FastMCP
from carla_mcp.tool_proxy import discover_and_register, unregister_all, _registered_tools


@pytest.mark.asyncio
async def test_two_backends_with_prefixes():
    """Simulate discovering tools from two backends, verify no collisions."""
    bridge = FastMCP("Test Bridge")
    _registered_tools.clear()

    carla_tools = [
        MagicMock(name="x", description="Save Carla project",
                  inputSchema={"properties": {"filename": {"type": "string"}}, "required": ["filename"]}),
    ]
    looper_tools = [
        MagicMock(name="x", description="Save looper session",
                  inputSchema={"properties": {"path": {"type": "string"}}, "required": ["path"]}),
    ]

    # Fix the name attribute on MagicMock (it conflicts with MagicMock's own .name)
    carla_tools[0].name = "save_project"
    looper_tools[0].name = "save_session"

    for tools, prefix in [(carla_tools, "carla"), (looper_tools, "looper")]:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.tools = tools
        mock_session.list_tools = AsyncMock(return_value=mock_result)
        mock_session.initialize = AsyncMock()
        with patch("carla_mcp.tool_proxy.sse_client") as mock_sse:
            mock_sse.return_value.__aenter__ = AsyncMock(
                return_value=(AsyncMock(), AsyncMock())
            )
            with patch("carla_mcp.tool_proxy.ClientSession") as mock_cs:
                mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
                await discover_and_register(bridge, f"http://localhost:0/sse", prefix=prefix)

    assert "carla_save_project" in _registered_tools
    assert "looper_save_session" in _registered_tools
    assert len(_registered_tools) == 2

    # Unregister only carla
    removed = unregister_all(bridge, prefix="carla")
    assert removed == 1
    assert "looper_save_session" in _registered_tools
    assert "carla_save_project" not in _registered_tools


@pytest.mark.asyncio
async def test_restart_one_backend_preserves_other():
    """Restarting one backend (unregister + discover) doesn't affect the other."""
    bridge = FastMCP("Test Bridge")
    _registered_tools.clear()
    _registered_tools.update({"carla_foo", "looper_bar"})

    # Simulate Carla restart: unregister carla, re-discover carla
    unregister_all(bridge, prefix="carla")
    assert _registered_tools == {"looper_bar"}
