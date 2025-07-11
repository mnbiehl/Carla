# Carla MCP Audio Routing Guide for LLM Agents

This guide explains how to use the Carla MCP (Model Context Protocol) server to create complex audio routing setups, connecting external JACK applications through Carla's powerful plugin host.

## Overview

The Carla MCP allows you to:
- Control Carla's plugin host programmatically
- Route audio between external JACK applications and Carla plugins
- Manage connections in Carla's patchbay mode
- Apply effects and processing to external audio sources

## Key Concepts

### 1. Audio Flow Architecture
```
External App (e.g., Loopers) → JACK → Carla Input → Plugin Effects → Carla Output → System Speakers
```

### 2. Connection Types
- **External JACK connections**: Use `jack_connect` CLI commands
- **Internal Carla connections**: Use MCP patchbay tools

### 3. Important: Group ID Offset
The Carla backend uses 1-based group IDs internally, while the MCP API shows 0-based IDs. The MCP tools handle this automatically.

## Common Workflow: Processing External Audio

### Step 1: Switch to Patchbay Mode
```python
mcp__carla-mcp__switch_to_patchbay_mode()
```
Patchbay mode allows flexible routing between plugins and I/O.

### Step 2: Connect External Application to Carla
Use JACK CLI to connect external apps to Carla's inputs:
```bash
# Example: Connect a looper to Carla
jack_connect loopers:loop0_out_l Carla:audio-in1
jack_connect loopers:loop0_out_r Carla:audio-in1  # Mono sum for stereo sources
```

### Step 3: Add Audio Plugins
```python
# Search for available plugins
mcp__carla-mcp__search_plugins(query="reverb", limit=10)

# Add plugin by name
mcp__carla-mcp__add_plugin_by_name(plugin_name="Dragonfly Room Reverb")
```

### Step 4: Connect Audio Through Plugins
```python
# List available groups to see port names
mcp__carla-mcp__get_patchbay_groups()

# Connect Carla input to plugin
mcp__carla-mcp__connect_patchbay_ports(
    group_a_name="Audio Input",
    port_a_name="Capture 1",
    group_b_name="Dragonfly Room Reverb",
    port_b_name="Audio Input 1"
)

# For mono-to-stereo processing, connect to both inputs
mcp__carla-mcp__connect_patchbay_ports(
    group_a_name="Audio Input",
    port_a_name="Capture 1",
    group_b_name="Dragonfly Room Reverb", 
    port_b_name="Audio Input 2"
)

# Connect plugin output to system
mcp__carla-mcp__connect_patchbay_ports(
    group_a_name="Dragonfly Room Reverb",
    port_a_name="Audio Output 1",
    group_b_name="Audio Output",
    port_b_name="Playback 1"
)
```

### Step 5: Verify Connections
```python
# Check JACK connections
Bash(command="jack_lsp -c | grep Carla")

# Check Carla internal connections
mcp__carla-mcp__list_patchbay_connections()
```

## Managing Connections

### List All Connections
```python
connections = mcp__carla-mcp__list_patchbay_connections()
# Returns JSON with connection IDs and details
```

### Disconnect Specific Connection
```python
mcp__carla-mcp__disconnect_patchbay_connection(connection_id=1)
```

## Plugin Control

### Basic Plugin Operations
```python
# List loaded plugins
mcp__carla-mcp__list_loaded_plugins()

# Set plugin active/bypass
mcp__carla-mcp__set_plugin_active(plugin_id=0, active=False)

# Adjust volume
mcp__carla-mcp__set_plugin_volume(plugin_id=0, volume=0.8)

# Set parameters
mcp__carla-mcp__get_plugin_info(plugin_id=0)  # Get parameter list
mcp__carla-mcp__set_plugin_parameter(plugin_id=0, parameter_id=1, value=0.5)
```

## Common Audio Routing Patterns

### 1. Simple Effects Chain
```
External Audio → Carla Input → Effect 1 → Effect 2 → Carla Output → Speakers
```

### 2. Parallel Processing
```
External Audio → Carla Input ┬→ Effect 1 →┐
                             └→ Effect 2 →┴→ Mixer → Output
```

### 3. Mono to Stereo Processing
```
Mono External → Carla Input 1 ┬→ Plugin L Input
                              └→ Plugin R Input
```

## Tips and Best Practices

1. **Always check current mode**: Some operations only work in patchbay mode
2. **Use `get_patchbay_groups()` frequently**: Port names may vary by plugin
3. **External connections persist**: JACK connections remain until explicitly disconnected
4. **Plugin IDs are 0-based**: First plugin is ID 0
5. **Save sessions**: Use Carla's session management for complex setups

## Troubleshooting

### Connection Fails
- Verify you're in patchbay mode
- Check group and port names match exactly (case-sensitive)
- Ensure audio types match (audio→audio, not audio→MIDI)

### No Sound
- Check JACK connections: `jack_lsp -c`
- Verify plugin is active: `set_plugin_active(plugin_id, True)`
- Check volume levels: `set_plugin_volume(plugin_id, 1.0)`

### Plugin Not Found
- Run plugin discovery: `discover_all_plugins()`
- Search with partial names: `search_plugins("reverb")`
- Check plugin type filter if specified

## Example: Complete Looper Effects Setup

```python
# 1. Setup
mcp__carla-mcp__switch_to_patchbay_mode()

# 2. External connection (in Bash)
Bash("jack_connect loopers:loop0_out_l Carla:audio-in1")
Bash("jack_connect loopers:loop0_out_r Carla:audio-in1")

# 3. Add reverb
mcp__carla-mcp__add_plugin_by_name("TAP Reverberator")

# 4. Route through reverb
mcp__carla-mcp__connect_patchbay_ports("Audio Input", "Capture 1", "TAP Reverberator", "Input L")
mcp__carla-mcp__connect_patchbay_ports("Audio Input", "Capture 1", "TAP Reverberator", "Input R")
mcp__carla-mcp__connect_patchbay_ports("TAP Reverberator", "Output L", "Audio Output", "Playback 1")
mcp__carla-mcp__connect_patchbay_ports("TAP Reverberator", "Output R", "Audio Output", "Playback 2")

# 5. Adjust reverb
mcp__carla-mcp__set_plugin_parameter(0, 0, 0.3)  # Adjust wet/dry mix
```

This creates a complete audio path from your looper through reverb to the speakers!