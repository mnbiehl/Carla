# Carla MCP Redesign

## Overview

Complete redesign of the Carla MCP server for live looping performance. The primary use case is applying effects to live loop tracks from the looperdooper application via JACK.

### Goals
- Reliable audio routing that the AI can control without confusion
- Parallel effects processing for multiple loop tracks
- Simple, high-level API that hides internal complexity
- Template system for saving and reusing configurations

### Non-Goals
- Modifying Carla's C++ core engine
- Supporting non-JACK audio backends
- GUI integration (headless operation is fine)

## Architecture

### Three-Layer Design

```
┌─────────────────────────────────────────────────────────┐
│  AI (Claude)                                            │
│  Speaks in human terms: "connect looper:out_1 to Reverb"│
└─────────────────────────┬───────────────────────────────┘
                          │ MCP Protocol
┌─────────────────────────▼───────────────────────────────┐
│  MCP Server (Python) - REWRITTEN                        │
│  - State Manager: tracks connections, chains, templates │
│  - Multi-instance Manager: spawns/controls Carla procs  │
│  - High-level tools: create_chain, connect, save/load   │
│  - Resolves names → Carla IDs internally                │
└─────────────────────────┬───────────────────────────────┘
                          │ Carla Python API (per instance)
┌─────────────────────────▼───────────────────────────────┐
│  Carla Instances (multiple processes)                   │
│  - Each instance handles one or more effects chains     │
│  - OS schedules across CPU cores (natural parallelism)  │
│  - Connected via JACK                                   │
└─────────────────────────────────────────────────────────┘
```

### Multi-Instance Parallelism

Instead of complex C++ parallel processing code, we use multiple Carla processes. Each process naturally runs on its own CPU core(s).

```
looper:out_1 ─→ [Carla Instance 1: Comp→Reverb] ─→ ┐
looper:out_2 ─→ [Carla Instance 2: Dist→Delay] ─→ ├─→ Master/Output
looper:out_3 ─→ [Carla Instance 3: Chorus→EQ]  ─→ ┘
```

**Latency impact:** +1 JACK buffer (~2.7ms at 128 samples/48kHz) compared to single instance. Acceptable for live performance.

**Benefits:**
- No C++ modifications needed
- Process isolation (one chain crashing doesn't kill everything)
- Simpler to implement and debug

## State Manager

The State Manager maintains a complete picture of the audio world so the AI doesn't have to track IDs and ports.

### What It Tracks

```
StateManager
├── Instances
│   └── {"main": CarlaInstance, "loop1-fx": CarlaInstance, ...}
│
├── Aliases (user-defined names for ports)
│   └── {"Guitar Loop": "looper:out_1", ...}
│
├── Chains (named routing groups)
│   └── {"Vocal Chain": {instance: "main", path: [src, plugin, dst]}}
│
├── Connections (current state, by name not ID)
│   └── Set of (source, destination) tuples
│
└── Templates (saved configurations)
    └── {"Live Set A": {plugins, chains, params, aliases}}
```

### Name Resolution

The State Manager uses JACK/Carla native names directly. Additional behavior:

1. **Exact names execute immediately** - "connect looper:out_1_L to Calf Reverb:In L"
2. **Partial names return candidates** - "connect looper to reverb" returns matches for confirmation
3. **User-defined aliases** - Optional shortcuts like "Guitar Loop" for "looper:out_1"

### Stereo Handling

Stereo pairs are the default unit, not individual channels.

| Source | Destination | Default Behavior |
|--------|-------------|------------------|
| Stereo → Stereo | L→L, R→R |
| Stereo → Mono | Sum L+R to mono input |
| Mono → Stereo | Duplicate mono to both L and R |
| Mono → Mono | Direct connection |

Stereo pair detection recognizes: `_L/_R`, `_left/_right`, `_1/_2`

Override with explicit channel specification: "connect looper:out_1_L to Calf Reverb:In L"

## Tool API

### Discovery Tools

```python
list_ports()
# Returns all JACK ports and Carla plugins, grouped logically
# {
#   "sources": ["looper:out_1 (stereo)", "looper:out_2 (stereo)"],
#   "plugins": {"main": ["Calf Reverb (stereo)"], "fx1": ["Compressor (mono)"]},
#   "destinations": ["system:playback (stereo)"]
# }

list_connections()
# Returns current routing state by name

list_instances()
# Returns running Carla instances and their status

list_templates()
# Returns saved templates
```

### Instance Management

```python
create_instance(name)
# Spawns new headless Carla process

remove_instance(name)
# Gracefully stops instance
```

### Routing Tools

```python
connect(source, destination, mode="auto")
# mode: "auto" (smart stereo/mono), "left", "right", "sum", "duplicate"
# Exact names execute immediately
# Partial names return candidates for confirmation

disconnect(source, destination)
# Removes connection(s)

create_chain(name, components[], instance="auto")
# Creates all connections in one call
# Handles stereo/mono conversions automatically
# "auto" instance picks one with capacity, or specify explicitly

delete_chain(name)
# Removes all connections in the chain
```

### Template Tools

```python
save_template(name, include_params=True)
# Saves: plugins, chains, connections, aliases, optionally parameter values

load_template(name, merge=False)
# Restores saved state
# merge=True applies on top of current state

export_to_carla(filepath)
# Saves as .carxp Carla project

import_from_carla(filepath)
# Loads .carxp into MCP state
```

### Alias Tools

```python
create_alias(alias, target)
# "create_alias('Guitar Loop', 'looper:out_1')"

remove_alias(alias)

list_aliases()
```

### Plugin Control

```python
add_plugin(name_or_uri, instance="main")
# Adds plugin by fuzzy name match or exact URI

remove_plugin(plugin, instance="main")

set_param(plugin, param, value)
# "set_param('Reverb', 'decay', 0.7)"

get_params(plugin)
# Returns all parameters with current values
```

## Template System

### Storage Locations

**MCP-managed templates** (portable across sessions):
```
~/.config/carla-mcp/templates/
├── live-set-a.json
├── ambient-practice.json
└── guitar-chain.json
```

**Carla project integration:**
- `export_to_carla()` writes `.carxp` files
- `import_from_carla()` reads `.carxp` and rebuilds MCP state

### Template Contents

```json
{
  "name": "Live Set A",
  "created": "2026-01-26",
  "instances": ["main", "loop1-fx", "loop2-fx"],
  "plugins": {
    "main": [
      {"name": "Calf Reverb", "uri": "lv2:...", "params": {"decay": 0.7}}
    ]
  },
  "aliases": {
    "Guitar Loop": "looper:out_1"
  },
  "chains": [
    {"name": "Guitar FX", "instance": "loop1-fx", "path": ["looper:out_1", "Compressor", "Calf Reverb", "system:playback"]}
  ]
}
```

### Partial Templates

Save/load subsets:
```python
save_template("just reverb settings", plugins=["Calf Reverb"])
load_template("just reverb settings", merge=True)  # Applies without touching other state
```

## Code Changes

### Delete (C++ parallel processing - unused)
- `source/backend/engine/CarlaEngineGraphParallelV2.cpp`
- `source/backend/engine/CarlaEngineGraphParallelV2.hpp`
- `source/backend/engine/CarlaEngineDependencyGraph.*` (if exists)
- `source/backend/engine/CarlaEngineThreadPool.*` (if exists)
- `source/backend/engine/CarlaEngineBufferPool.*` (if exists)

### Rewrite (Python MCP layer)
- `source/frontend/carla_mcp/main.py` - Simpler initialization, multi-instance support
- `source/frontend/carla_mcp/backend/backend_bridge.py` - Split into focused modules
- `source/frontend/carla_mcp/tools/*.py` - New tool API

### New (Python)
- `source/frontend/carla_mcp/state/state_manager.py` - Core state tracking
- `source/frontend/carla_mcp/state/instance_manager.py` - Multi-instance lifecycle
- `source/frontend/carla_mcp/state/chain_manager.py` - Chain operations
- `source/frontend/carla_mcp/templates/template_manager.py` - Save/load templates

### Keep (working code)
- `source/frontend/carla_mcp/discovery/` - Plugin discovery works fine
- `source/frontend/carla_mcp/utils/logging.py` - Logging setup is fine
- Carla C++ core engine - Untouched

## Implementation Order

### Phase 1: Foundation
1. State Manager skeleton
2. Multi-instance spawning (headless Carla processes)
3. Basic JACK port discovery

### Phase 2: Core Routing
4. `connect` / `disconnect` with exact names
5. Stereo pair detection and handling
6. Partial name matching with confirmation flow
7. `create_chain` / `delete_chain`

### Phase 3: Templates & Aliases
8. Alias system
9. Template save/load (MCP format)
10. Carla project export/import

### Phase 4: Cleanup
11. Delete C++ parallel processing code
12. Remove dead Python code (unused validation module, debug prints)
13. Documentation

### Testing Strategy
- Real looper connected via JACK at each phase
- Actual LV2 effects (not mocks)
- Verify latency stays within acceptable range
- Test instance crash recovery

## Open Questions

1. **Instance load balancing** - How smart should "auto" instance selection be? Simple round-robin, or track CPU usage?

2. **Carla GUI** - Support optional GUI mode per instance, or headless only?

3. **Hot reload** - If MCP server restarts, can it reconnect to existing Carla instances?

4. **MIDI routing** - Should MIDI control (note on/off, CC) go through MCP or direct JACK MIDI?
