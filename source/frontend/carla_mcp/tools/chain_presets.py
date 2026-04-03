"""Chain preset save/load tools for Carla MCP Server."""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge
from .chain_builder import build_chain
from ..utils.pw_link import ensure_carla_to_monitors

logger = logging.getLogger(__name__)

CHAIN_PRESET_DIR = Path.home() / ".config" / "rig-sessions" / "chain-presets"


def save_chain_preset_impl(
    bridge: CarlaBackendBridge,
    name: str,
    plugin_ids: List[int],
) -> dict:
    """Save the current chain state (plugin names + parameters) to a JSON preset."""
    if not plugin_ids:
        return {"success": False, "error": "No plugin IDs specified"}

    plugins_data = []
    for pid in plugin_ids:
        info = bridge.get_plugin_info(pid)
        if info is None:
            return {"success": False, "error": f"Plugin ID {pid} not found"}

        params = bridge.get_all_parameter_details(pid)
        param_dict = {p["name"]: p["value"] for p in params}
        plugins_data.append({"name": info["name"], "parameters": param_dict})

    preset = {"version": 1, "name": name, "plugins": plugins_data}

    CHAIN_PRESET_DIR.mkdir(parents=True, exist_ok=True)
    preset_path = CHAIN_PRESET_DIR / f"{name}.json"
    preset_path.write_text(json.dumps(preset, indent=2))

    return {"success": True, "path": str(preset_path)}


def load_chain_preset_impl(
    bridge: CarlaBackendBridge,
    name: str,
    connect_system_input: bool = True,
    connect_system_output: bool = True,
) -> dict:
    """Load a chain preset: rebuild plugin chain and restore parameters."""
    preset_path = CHAIN_PRESET_DIR / f"{name}.json"
    if not preset_path.exists():
        return {"success": False, "error": f"Preset '{name}' not found"}

    preset = json.loads(preset_path.read_text())
    plugin_names = [p["name"] for p in preset["plugins"]]

    chain_result = build_chain(
        bridge, plugin_names, connect_system_input, connect_system_output
    )
    if not chain_result["success"]:
        return chain_result

    warnings = []
    for i, preset_plugin in enumerate(preset["plugins"]):
        pid = chain_result["plugins"][i]["id"]
        current_params = bridge.get_all_parameter_details(pid)
        name_to_id = {p["name"]: p["id"] for p in current_params}

        for param_name, param_value in preset_plugin["parameters"].items():
            if param_name in name_to_id:
                bridge.set_parameter_value(pid, name_to_id[param_name], param_value)
            else:
                warnings.append(
                    f"Plugin '{preset_plugin['name']}': parameter '{param_name}' not found"
                )

    result = {
        "success": True,
        "plugins": chain_result["plugins"],
        "connections": chain_result["connections"],
    }
    if warnings:
        result["warnings"] = warnings

    if connect_system_output:
        result["external_monitors"] = ensure_carla_to_monitors()

    return result


def list_chain_presets_impl() -> List[Dict[str, Any]]:
    """List all saved chain presets."""
    if not CHAIN_PRESET_DIR.exists():
        return []

    presets = []
    for path in sorted(CHAIN_PRESET_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            presets.append({
                "name": data["name"],
                "plugin_count": len(data["plugins"]),
                "plugins": [p["name"] for p in data["plugins"]],
            })
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Skipping invalid preset file %s: %s", path, e)

    return presets


def register_chain_preset_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register chain preset MCP tools."""

    @mcp.tool()
    def save_chain_preset(name: str, plugin_ids: List[int]) -> str:
        """Save a named chain preset with all plugin parameters.

        Captures plugin names and all parameter values for the specified
        plugin IDs. Saved to ~/.config/rig-sessions/chain-presets/{name}.json.

        Args:
            name: Preset name (e.g. "uke-chain", "guitar-lead").
            plugin_ids: List of plugin IDs to include (e.g. [0, 1, 2]).
        """
        result = save_chain_preset_impl(bridge, name, plugin_ids)
        return json.dumps(result, indent=2)

    @mcp.tool()
    def load_chain_preset(
        name: str,
        connect_system_input: bool = True,
        connect_system_output: bool = True,
    ) -> str:
        """Load a chain preset: adds plugins, wires them, restores parameters.

        Builds the full effects chain from the saved preset, auto-detects
        mono/stereo routing, and applies all saved parameter values.
        If connect_system_output is True, also verifies/creates the
        external Carla-to-monitors connection.

        Args:
            name: Preset name to load.
            connect_system_input: Wire system audio input to first plugin.
            connect_system_output: Wire last plugin to system output + monitors.
        """
        result = load_chain_preset_impl(
            bridge, name,
            connect_system_input=connect_system_input,
            connect_system_output=connect_system_output,
        )
        return json.dumps(result, indent=2)

    @mcp.tool()
    def list_chain_presets() -> str:
        """List available chain presets.

        Shows all saved chain presets with their plugin lists.
        """
        presets = list_chain_presets_impl()
        if not presets:
            return json.dumps({"presets": [], "message": "No chain presets saved yet."})
        return json.dumps({"presets": presets}, indent=2)
