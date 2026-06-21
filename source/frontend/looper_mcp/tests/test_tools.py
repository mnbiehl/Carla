import pytest
from unittest.mock import AsyncMock
from looper_mcp.tools import (
    _command_for_transport,
    _command_for_looper,
    register_tools,
)


def test_transport_start_command():
    assert _command_for_transport("start") == "Start"


def test_transport_set_tempo_command():
    assert _command_for_transport("set_tempo", bpm=120.0) == {"SetTempoBPM": 120.0}


def test_transport_set_time_signature():
    assert _command_for_transport("set_time_signature", upper=4, lower=4) == {
        "SetTimeSignature": [4, 4]
    }


def test_looper_record_command():
    assert _command_for_looper("record", target="Selected") == {
        "Looper": ["Record", "Selected"]
    }


def test_looper_record_with_index():
    assert _command_for_looper("record", target="0") == {
        "Looper": ["Record", {"Index": 0}]
    }


def test_looper_record_all():
    assert _command_for_looper("record", target="All") == {
        "Looper": ["Record", "All"]
    }


def test_looper_set_level():
    assert _command_for_looper("set_level", target="Selected", value=0.5) == {
        "Looper": [{"SetLevel": 0.5}, "Selected"]
    }


def test_looper_set_pan():
    assert _command_for_looper("set_pan", target="1", value=-0.5) == {
        "Looper": [{"SetPan": -0.5}, {"Index": 1}]
    }


def test_looper_test_tone_enable():
    assert _command_for_looper("test_tone", target="Selected", enabled=True) == {
        "Looper": [{"TestTone": True}, "Selected"]
    }


def test_looper_test_tone_disable_with_index():
    assert _command_for_looper("test_tone", target="0", enabled=False) == {
        "Looper": [{"TestTone": False}, {"Index": 0}]
    }


def test_test_tone_tool_is_registered():
    """register_tools must register a `test_tone` MCP tool."""
    tools = {}

    class _MCP:
        def tool(self):
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator

    register_tools(_MCP(), AsyncMock())
    assert "test_tone" in tools


@pytest.mark.asyncio
async def test_test_tone_tool_sends_command():
    """The test_tone tool must send the TestTone command over the client."""
    tools = {}

    class _MCP:
        def tool(self):
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator

    client = AsyncMock()
    client.send_command = AsyncMock(return_value={"ok": True})
    register_tools(_MCP(), client)

    result = await tools["test_tone"](enabled=True, target="0")

    client.send_command.assert_awaited_once_with(
        {"Looper": [{"TestTone": True}, {"Index": 0}]}
    )
    assert result == "OK"
