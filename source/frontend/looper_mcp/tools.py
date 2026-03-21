"""MCP tool definitions for looperdooper control."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_target(target: str):
    """Parse a looper target string into serde JSON format."""
    if target == "Selected":
        return "Selected"
    if target == "All":
        return "All"
    try:
        return {"Index": int(target)}
    except ValueError:
        try:
            return {"Id": int(target)}
        except ValueError:
            return "Selected"


# Simple transport commands (unit variants)
_SIMPLE_TRANSPORT = {
    "start": "Start",
    "stop": "Stop",
    "pause": "Pause",
    "start_stop": "StartStop",
    "play_pause": "PlayPause",
    "reset": "Reset",
}

# Simple looper commands (unit variants of LooperCommand)
_SIMPLE_LOOPER = {
    "record": "Record",
    "overdub": "Overdub",
    "play": "Play",
    "mute": "Mute",
    "solo": "Solo",
    "clear": "Clear",
    "delete": "Delete",
    "record_overdub_play": "RecordOverdubPlay",
    "record_play_overdub": "RecordPlayOverdub",
    "undo": "Undo",
    "redo": "Redo",
    "cycle_monitor_mode": "CycleMonitorMode",
}


def _command_for_transport(action: str, **kwargs):
    """Build a serde-compatible Command JSON for transport actions."""
    if action in _SIMPLE_TRANSPORT:
        return _SIMPLE_TRANSPORT[action]
    if action == "set_tempo":
        return {"SetTempoBPM": kwargs["bpm"]}
    if action == "set_time_signature":
        return {"SetTimeSignature": [kwargs["upper"], kwargs["lower"]]}
    if action == "set_metronome_level":
        return {"SetMetronomeLevel": kwargs["level"]}
    if action == "set_quantization_mode":
        return {"SetQuantizationMode": kwargs["mode"]}
    raise ValueError(f"Unknown transport action: {action}")


def _command_for_looper(action: str, target: str = "Selected", **kwargs):
    """Build a serde-compatible Command JSON for looper actions."""
    parsed_target = _parse_target(target)
    if action in _SIMPLE_LOOPER:
        return {"Looper": [_SIMPLE_LOOPER[action], parsed_target]}
    if action == "set_level":
        return {"Looper": [{"SetLevel": kwargs["value"]}, parsed_target]}
    if action == "set_pan":
        return {"Looper": [{"SetPan": kwargs["value"]}, parsed_target]}
    if action == "set_speed":
        return {"Looper": [{"SetSpeed": kwargs["speed"]}, parsed_target]}
    raise ValueError(f"Unknown looper action: {action}")


def register_tools(mcp_server, looper_client):
    """Register all looper MCP tools with the FastMCP server."""

    @mcp_server.tool()
    async def transport_start() -> str:
        """Start the looper transport (begin playback/recording clock)."""
        result = await looper_client.send_command(_command_for_transport("start"))
        return _format_result(result)

    @mcp_server.tool()
    async def transport_stop() -> str:
        """Stop the looper transport."""
        result = await looper_client.send_command(_command_for_transport("stop"))
        return _format_result(result)

    @mcp_server.tool()
    async def transport_pause() -> str:
        """Pause the looper transport."""
        result = await looper_client.send_command(_command_for_transport("pause"))
        return _format_result(result)

    @mcp_server.tool()
    async def transport_start_stop() -> str:
        """Toggle transport start/stop."""
        result = await looper_client.send_command(_command_for_transport("start_stop"))
        return _format_result(result)

    @mcp_server.tool()
    async def transport_play_pause() -> str:
        """Toggle transport play/pause."""
        result = await looper_client.send_command(_command_for_transport("play_pause"))
        return _format_result(result)

    @mcp_server.tool()
    async def transport_reset() -> str:
        """Reset the looper transport to the beginning."""
        result = await looper_client.send_command(_command_for_transport("reset"))
        return _format_result(result)

    @mcp_server.tool()
    async def set_tempo(bpm: float) -> str:
        """Set the looper tempo in BPM."""
        result = await looper_client.send_command(
            _command_for_transport("set_tempo", bpm=bpm)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def set_time_signature(upper: int, lower: int) -> str:
        """Set the time signature (e.g., 4/4, 3/4, 6/8)."""
        result = await looper_client.send_command(
            _command_for_transport("set_time_signature", upper=upper, lower=lower)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def set_metronome_level(level: int) -> str:
        """Set metronome volume (0-100)."""
        result = await looper_client.send_command(
            _command_for_transport("set_metronome_level", level=level)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def set_quantization_mode(mode: str) -> str:
        """Set quantization mode: Free, Beat, or Measure."""
        result = await looper_client.send_command(
            _command_for_transport("set_quantization_mode", mode=mode)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def record(target: str = "Selected") -> str:
        """Start recording on a looper. Target: Selected, All, or looper index (0, 1, 2...)."""
        result = await looper_client.send_command(
            _command_for_looper("record", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def overdub(target: str = "Selected") -> str:
        """Start overdubbing on a looper."""
        result = await looper_client.send_command(
            _command_for_looper("overdub", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def play(target: str = "Selected") -> str:
        """Switch a looper to playback mode."""
        result = await looper_client.send_command(
            _command_for_looper("play", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def mute(target: str = "Selected") -> str:
        """Mute a looper."""
        result = await looper_client.send_command(
            _command_for_looper("mute", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def solo(target: str = "Selected") -> str:
        """Solo a looper."""
        result = await looper_client.send_command(
            _command_for_looper("solo", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def clear(target: str = "Selected") -> str:
        """Clear a looper's recorded audio."""
        result = await looper_client.send_command(
            _command_for_looper("clear", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def delete_looper(target: str = "Selected") -> str:
        """Delete a looper."""
        result = await looper_client.send_command(
            _command_for_looper("delete", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def record_overdub_play(target: str = "Selected") -> str:
        """Cycle through record -> overdub -> play states."""
        result = await looper_client.send_command(
            _command_for_looper("record_overdub_play", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def record_play_overdub(target: str = "Selected") -> str:
        """Cycle through record -> play -> overdub states."""
        result = await looper_client.send_command(
            _command_for_looper("record_play_overdub", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def undo(target: str = "Selected") -> str:
        """Undo the last action on a looper."""
        result = await looper_client.send_command(
            _command_for_looper("undo", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def redo(target: str = "Selected") -> str:
        """Redo the last undone action on a looper."""
        result = await looper_client.send_command(
            _command_for_looper("redo", target=target)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def set_looper_level(target: str, level: float) -> str:
        """Set a looper's volume level (0.0 to 1.0)."""
        result = await looper_client.send_command(
            _command_for_looper("set_level", target=target, value=level)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def set_looper_pan(target: str, pan: float) -> str:
        """Set a looper's pan position (-1.0 left to 1.0 right)."""
        result = await looper_client.send_command(
            _command_for_looper("set_pan", target=target, value=pan)
        )
        return _format_result(result)

    @mcp_server.tool()
    async def add_looper() -> str:
        """Add a new looper."""
        result = await looper_client.send_command("AddLooper")
        return _format_result(result)

    @mcp_server.tool()
    async def select_looper(index: int) -> str:
        """Select a looper by index (0, 1, 2...)."""
        result = await looper_client.send_command({"SelectLooperByIndex": index})
        return _format_result(result)

    @mcp_server.tool()
    async def select_previous_looper() -> str:
        """Select the previous looper."""
        result = await looper_client.send_command("SelectPreviousLooper")
        return _format_result(result)

    @mcp_server.tool()
    async def select_next_looper() -> str:
        """Select the next looper."""
        result = await looper_client.send_command("SelectNextLooper")
        return _format_result(result)

    @mcp_server.tool()
    async def previous_part() -> str:
        """Switch to the previous part (A, B, C, D)."""
        result = await looper_client.send_command("PreviousPart")
        return _format_result(result)

    @mcp_server.tool()
    async def next_part() -> str:
        """Switch to the next part."""
        result = await looper_client.send_command("NextPart")
        return _format_result(result)

    @mcp_server.tool()
    async def go_to_part(part: str) -> str:
        """Go to a specific part (A, B, C, or D)."""
        result = await looper_client.send_command({"GoToPart": part})
        return _format_result(result)

    @mcp_server.tool()
    async def mute_main_output() -> str:
        """Toggle mute on the main output."""
        result = await looper_client.send_command("MuteMainOutput")
        return _format_result(result)

    @mcp_server.tool()
    async def mute_all_outputs() -> str:
        """Toggle mute on all outputs."""
        result = await looper_client.send_command("MuteAllOutputs")
        return _format_result(result)

    @mcp_server.tool()
    async def save_session(path: str) -> str:
        """Save looper session to a file path."""
        result = await looper_client.send_command({"SaveSession": path})
        return _format_result(result)

    @mcp_server.tool()
    async def load_session(path: str) -> str:
        """Load a looper session from a file path."""
        result = await looper_client.send_command({"LoadSession": path})
        return _format_result(result)

    @mcp_server.tool()
    async def get_state() -> str:
        """Get the current looper engine state (tempo, looper count, levels, etc.)."""
        import json

        state = await looper_client.get_state()
        return json.dumps(state, indent=2)


def _format_result(result: dict) -> str:
    """Format a looperdooper response as a human-readable string."""
    if "ok" in result:
        return "OK"
    if "error" in result:
        return f"Error: {result['error']}"
    import json

    return json.dumps(result)
