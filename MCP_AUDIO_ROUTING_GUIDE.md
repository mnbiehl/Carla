# Carla MCP Audio Routing Guide for LLM Agents

This guide explains how to use the Carla MCP (Model Context Protocol) server to create audio routing setups, connecting looper tracks through Carla's plugin host for effects processing.

## Overview

The Carla MCP allows you to:
- Control Carla's plugin host programmatically in **patchbay mode only**
- Route looper tracks (stereo) to Carla mono inputs via JACK
- Process audio through plugin effects chains
- Output all processed audio to Carla outputs 1/2 (stereo)

## Key Concepts

### 1. Audio Flow Architecture
```
Looper Track (stereo L/R) → JACK → Carla Input (mono) → Plugin Effects → Carla Output 1/2 (stereo) → System Speakers
```

### 2. Routing Rules
- **Always use patchbay mode** - More flexible routing for effects chains
- **Looper connections**: Use `jack_connect` CLI to connect stereo looper outputs to mono Carla inputs
- **Output routing**: All effects chains route to Carla outputs 1/2 only

### 3. Connection Types
- **External JACK connections**: Use `jack_connect` CLI commands for looper → Carla
- **Internal Carla connections**: Use MCP patchbay tools for plugin routing

## Standard Workflow: Processing Looper Tracks

### Step 1: Ensure Patchbay Mode (Should Already Be Active)
```python
# Carla should always be in patchbay mode
mcp__carla-mcp__get_current_engine_mode()  # Verify mode
```

### Step 2: Connect Looper Track to Carla Input
Connect both stereo outputs from a looper track to a single Carla mono input:
```bash
# Connect looper track 0 (stereo) to Carla input 1 (mono)
jack_connect loopers:loop0_out_l Carla:audio-in1
jack_connect loopers:loop0_out_r Carla:audio-in1

# For additional tracks, use different Carla inputs
jack_connect loopers:loop1_out_l Carla:audio-in2
jack_connect loopers:loop1_out_r Carla:audio-in2
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

# Connect plugin outputs to Carla outputs 1/2 ONLY
mcp__carla-mcp__connect_patchbay_ports(
    group_a_name="Dragonfly Room Reverb",
    port_a_name="Audio Output 1",
    group_b_name="Audio Output",
    port_b_name="Playback 1"
)
mcp__carla-mcp__connect_patchbay_ports(
    group_a_name="Dragonfly Room Reverb",
    port_a_name="Audio Output 2",
    group_b_name="Audio Output",
    port_b_name="Playback 2"
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

### A/B Testing with Plugin Bypass

For A/B testing effects, use **bypass mode** instead of deactivating plugins. Bypass keeps the plugin in the audio chain but routes 100% dry signal through it:

```python
# BYPASS vs ACTIVE - Key Differences:
# set_plugin_active(False) = Removes plugin from audio chain completely
# Bypass mode = Keeps plugin loaded but passes 100% dry signal

# Most plugins have a dry/wet parameter (often parameter 0)
# Get parameter details first:
mcp__carla-mcp__get_plugin_parameters(plugin_id=0)

# Bypass plugin (100% dry signal)
mcp__carla-mcp__set_plugin_parameter(plugin_id=0, parameter_id=0, value=0.0)

# Restore processing (100% wet signal) 
mcp__carla-mcp__set_plugin_parameter(plugin_id=0, parameter_id=0, value=1.0)

# Partial blend (50% wet/dry mix)
mcp__carla-mcp__set_plugin_parameter(plugin_id=0, parameter_id=0, value=0.5)
```

### Quick A/B Testing Examples
```python
# Example: A/B test reverb on plugin 0
mcp__carla-mcp__set_plugin_parameter(0, 0, 0.0)  # Bypass - dry only
mcp__carla-mcp__set_plugin_parameter(0, 0, 1.0)  # Process - wet only

# Example: A/B test compressor on plugin 1  
mcp__carla-mcp__set_plugin_parameter(1, 0, 0.0)  # Uncompressed
mcp__carla-mcp__set_plugin_parameter(1, 0, 1.0)  # Compressed

# Note: Check parameter names with get_plugin_parameters() first
# Dry/wet might not always be parameter 0
```

## Standard Audio Routing Pattern

### Looper to Effects Chain (Our Standard Setup)
```
Looper Track (stereo) → JACK → Carla Input N (mono) → Effects Chain → Carla Output 1/2 (stereo) → Speakers
```

### Key Points:
- Each looper track connects to its own Carla input (mono summed)
- All effects chains output to Carla outputs 1/2 only
- Multiple tracks can be processed through different effects chains
- All chains converge to the same stereo output pair

## Tips and Best Practices

1. **Carla is always in patchbay mode**: No need to switch modes
2. **One looper track per Carla input**: Connect both L/R to same input for mono sum
3. **All outputs to 1/2**: Every effects chain routes to Carla outputs 1/2 only
4. **Use `get_patchbay_groups()` frequently**: Port names may vary by plugin
5. **External connections persist**: JACK connections remain until explicitly disconnected
6. **Plugin IDs are 0-based**: First plugin is ID 0
7. **⚠️ Audio must flow before monitoring**: Don't enable auto-gain or check meters until audio connections are established - there's no point in monitoring silence!

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
# 1. Verify patchbay mode (should already be active)
mcp__carla-mcp__get_current_engine_mode()

# 2. Connect looper track 0 to Carla input 1 (mono sum)
Bash("jack_connect loopers:loop0_out_l Carla:audio-in1")
Bash("jack_connect loopers:loop0_out_r Carla:audio-in1")

# 3. Add reverb plugin
mcp__carla-mcp__add_plugin_by_name("TAP Reverberator")

# 4. Route: Carla Input 1 → Reverb → Carla Output 1/2
mcp__carla-mcp__connect_patchbay_ports("Audio Input", "Capture 1", "TAP Reverberator", "Input L")
mcp__carla-mcp__connect_patchbay_ports("Audio Input", "Capture 1", "TAP Reverberator", "Input R")
mcp__carla-mcp__connect_patchbay_ports("TAP Reverberator", "Output L", "Audio Output", "Playback 1")
mcp__carla-mcp__connect_patchbay_ports("TAP Reverberator", "Output R", "Audio Output", "Playback 2")

# 5. Adjust reverb parameters
mcp__carla-mcp__set_plugin_parameter(0, 0, 0.3)  # Adjust wet/dry mix
```

This creates a mono-summed input from your looper, processes it through reverb, and outputs stereo to Carla outputs 1/2!