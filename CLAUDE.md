# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Carla MCP Server provides AI control over Carla audio plugin host via the Model Context Protocol. The project combines a C++ audio processing engine (Carla) with a Python MCP frontend using FastMCP framework.

## Build Commands

### C++ Backend
```bash
# Full build (release)
make -j$(nproc)

# Debug build
make DEBUG=true -j$(nproc)

# Build specific targets
make backend          # libcarla_standalone2.so
make frontend         # Python/Qt frontend
make discovery        # carla-discovery-native tool

# Clean and rebuild
make clean && make -j$(nproc)
```

### Python Frontend
```bash
# Install dependencies
uv sync

# Run MCP server (standalone testing)
uv run python -m carla_mcp.main

# Run with development tools
uv run mcp dev source/frontend/carla_mcp/main.py
```

### Testing
```bash
# Python tests (pytest) - ALWAYS use uv run
uv run pytest

# Run specific test file
uv run pytest source/frontend/carla_mcp/tests/test_tools_discovery.py -v
```

## Architecture

### Two-Layer Architecture

**C++ Backend** (`source/backend/`): Carla audio engine with plugin processing
- `engine/CarlaEngine*.cpp` - Core audio processing engine
- `engine/CarlaEngineGraphParallelV2.*` - Modern C++20 parallel plugin processing (in development)
- `plugin/Carla*.cpp` - Plugin format implementations (LV2, VST2, VST3, etc.)

**Python Frontend** (`source/frontend/carla_mcp/`): MCP server exposing Carla control
- `main.py` - FastMCP server initialization, tool/resource registration
- `backend/backend_bridge.py` - `CarlaBackendBridge` wraps Carla's Python API
- `tools/*.py` - MCP tools (plugins, parameters, routing, MIDI, etc.)
- `resources/*.py` - MCP resources (status, monitoring, help)
- `discovery/` - Plugin discovery using `carla-discovery-native`
- `constants.py` - Single source of truth for Carla constants

### Communication Flow
```
Claude AI <-> MCP Protocol (SSE) <-> FastMCP Server <-> CarlaBackendBridge <-> Carla Engine
```

The MCP server runs on `localhost:3001` using SSE transport. It communicates directly with Carla's Python backend API (no OSC overhead).

### Key Design Decisions

1. **MCP server is decoupled from engine lifecycle** - Server stays running even when Carla engine restarts, preventing Wayland crashes

2. **Constants imported from carla_backend** - `constants.py` imports actual values from `carla_backend.py` with fallbacks. Critical fix: plugin type constants were previously off-by-one (e.g., PLUGIN_LV2 must be 4, not 3)

3. **Patchbay port offsets** - Input ports use offset 255, output ports use 510, multiplied by group_id * 1000

4. **LV2 plugin loading** - Pass bundle directory path (not .so file), empty filename, URI in label field

## Current Branch: parallel-plugin-processing

This branch implements multi-Carla instance orchestration for parallel effects processing.

## Plugin Support

Supported formats: LV2, LADSPA, VST2, VST3, DSSI, SF2, SFZ, JACK, JSFX, CLAP, AU (macOS)

Plugin discovery caches results in SQLite database. Discovery uses `carla-discovery-native` subprocess.

## MCP Tools Available

- **Connection**: `test_carla_connection`, engine status
- **Plugins**: `add_plugin_by_name`, `remove_plugin`, `list_loaded_plugins`, `search_plugins`
- **Parameters**: `get_plugin_parameters`, `set_plugin_parameter`
- **Routing**: `get_patchbay_groups`, `connect_patchbay_ports`, `switch_to_patchbay_mode`
- **MIDI**: `send_midi_note_on`, `send_midi_note_off`
- **Auto-gain**: automatic gain staging tools
- **Sessions**: `save_project`, `load_project`

## File Locations

- Main Makefile: `./Makefile`
- C++ source: `source/backend/`, `source/modules/`
- Python MCP: `source/frontend/carla_mcp/`
- Build output: `build/modules/{Debug,Release}/`
- Binaries: `bin/`
