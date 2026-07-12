---
name: audio-routing-workflow
description: Use when managing audio routing between JACK clients (loopers, Carla, audio interfaces), loading plugins in Carla, or setting up effects chains. Triggers include connecting ports, routing audio, monitoring inputs, adding effects, or any pw-jack/JACK operation.
---

# Audio Routing Workflow

## Overview

Two-level audio routing: **external PipeWire** connections between applications (loopers, Carla, Scarlett) using `pw-link`, and **internal Carla patchbay** connections between plugins using Carla's API. Always discover before connecting. Never guess port names.

## The Iron Rule

**Always run `pw-link -o` and `pw-link -i` before connecting anything.** PipeWire port names are long and unpredictable. Never guess them.

**Always use `pw-link` for external connections.** Do NOT use `pw-jack jack_connect` — it silently fails for Carla→Scarlett in PipeWire pro-audio mode.

## System Components

| Component | JACK Client Name | Port Pattern |
|-----------|-----------------|--------------|
| Scarlett 2i2 | `Focusrite Scarlett 2i2*` | `capture_AUX0/1`, `playback_AUX0/1` |
| Carla | `Carla` | `audio-in1..16`, `audio-out1..16` |
| Loopers | `loopers` | `in_l`, `in_r`, `main_out_l/r`, `loopN_out_l/r` (dynamic) |

**Loopers creates ports dynamically.** Each new loop adds `loopN_out_l` and `loopN_out_r`. Always re-discover ports after adding loops.

## Workflow

### 1. Discover (ALWAYS FIRST)

```bash
# List all output ports
pw-link -o

# List all input ports
pw-link -i

# List with current connections
pw-link -l

# Find specific client ports
pw-link -o | grep "Carla"
pw-link -i | grep "loopers"
```

### 2. External PipeWire Routing

Connect/disconnect between applications using `pw-link`:

```bash
# Connect (exact port names required - get from pw-link -o/-i)
pw-link "SOURCE:port" "DEST:port"

# Disconnect
pw-link -d "SOURCE:port" "DEST:port"
```

**The `start_rig` MCP tool handles standard connections automatically.** Use manual pw-link only for custom routing.

**Common patterns:**
```bash
# Scarlett input to Carla (monitoring)
pw-link "alsa_input.usb-Focusrite_Scarlett_2i2_USB-00.pro-input-0:capture_AUX0" "Carla:audio-in1"
pw-link "alsa_input.usb-Focusrite_Scarlett_2i2_USB-00.pro-input-0:capture_AUX1" "Carla:audio-in2"

# Scarlett input to loopers
pw-link "alsa_input.usb-Focusrite_Scarlett_2i2_USB-00.pro-input-0:capture_AUX0" "loopers:in_l"
pw-link "alsa_input.usb-Focusrite_Scarlett_2i2_USB-00.pro-input-0:capture_AUX1" "loopers:in_r"

# Loop track N to Carla inputs
pw-link "loopers:loop0_out_l" "Carla:audio-in3"
pw-link "loopers:loop0_out_r" "Carla:audio-in4"

# Carla output to Scarlett (monitors)
pw-link "Carla:audio-out1" "alsa_output.usb-Focusrite_Scarlett_2i2_USB-00.pro-output-0:playback_AUX0"
pw-link "Carla:audio-out2" "alsa_output.usb-Focusrite_Scarlett_2i2_USB-00.pro-output-0:playback_AUX1"
```

**Verify connections after creating them:** `pw-link -l | grep "Carla"`

### 3. Carla Plugin Management

```python
# Search for plugins
mcp__carla-mcp__search_plugins(query="compressor")

# Add by name (auto-discovers type)
mcp__carla-mcp__add_plugin_by_name(plugin_name="Calf Compressor")

# List loaded plugins (check IDs!)
mcp__carla-mcp__list_loaded_plugins()

# Get/set parameters
mcp__carla-mcp__get_plugin_parameters(plugin_id=0)
mcp__carla-mcp__set_plugin_parameter(plugin_id=0, parameter_id=1, value=0.5)
```

**Always call `list_loaded_plugins()` to confirm plugin IDs.** IDs shift when plugins are added or removed.

### 4. Internal Carla Patchbay Routing

Route audio between Carla's system inputs, plugins, and system outputs:

```python
# Build a complete chain in one call (preferred)
mcp__carla-mcp__build_effects_chain(
    plugins=["LSP Gate Mono", "LSP Compressor Mono", "Dragonfly Plate Reverb"],
    connect_system_input=True,
    connect_system_output=True
)

# Or manual routing (auto-detects mono/stereo):
mcp__carla-mcp__connect_system_to_plugin(system_input=3, plugin_id=0)  # auto-detect channels
mcp__carla-mcp__connect_plugins(source_plugin_id=0, dest_plugin_id=1)  # auto-detect channels
mcp__carla-mcp__connect_plugin_to_system(plugin_id=1, system_output_left=1)

# Explicit channel override still available:
mcp__carla-mcp__connect_system_to_plugin(system_input=9, plugin_id=0, channel="left")
mcp__carla-mcp__connect_system_to_plugin(system_input=10, plugin_id=0, channel="right")

# Verify
mcp__carla-mcp__list_patchbay_connections()
```

**Carla system inputs map to JACK inputs:** `Carla:audio-in3` = system input 3 inside patchbay.

**IMPORTANT: System inputs 1-2 are shared live inputs (Scarlett direct).** When connecting system input 1 or 2 to a new effects chain, you MUST first disconnect them from any existing chains they're already routed to. Otherwise the live signal goes through multiple chains simultaneously (e.g., guitar AND bass amp sim at once). Use `list_patchbay_connections()` to find and disconnect the old routes before adding new ones. Loop playback inputs (3+) don't have this problem since each loop output goes to its own dedicated Carla input.

### 5. Gain Staging

When splitting a source to multiple destinations (e.g., Scarlett to both Carla and loopers), check levels:

```python
mcp__carla-mcp__analyze_gain_staging(duration_seconds=5)
mcp__carla-mcp__set_plugin_volume(plugin_id=0, volume=0.8)  # 1.0 = unity, max 1.27
```

## Input Mapping Convention

Keep Carla inputs organized:

| Carla Input | Use |
|------------|-----|
| 1-2 | Scarlett direct (monitoring/processing) |
| 3-4 | Loop track 0 |
| 5-6 | Loop track 1 |
| 7-8 | Loop track 2 |
| 9-10 | Loop track 3 |
| 11+ | Additional sources |

**Duplicate loops share inputs.** If loop4 duplicates loop0, connect both to the same Carla input pair (3-4). Multiple JACK sources summing into one input is fine.

**Always wire loop outputs stereo: L→L, R→R.** Connect `loopN_out_l` to the chain's left input and `loopN_out_r` to the right. This preserves panning from within loopers.

**Mono plugins collapse stereo.** If you need L/R separation through an effects chain, use stereo plugin equivalents (e.g., x42-comp Stereo, x42-eq Stereo instead of C* Compress mono).

## Monitoring Patterns

**Direct monitoring (lowest latency):** Route Scarlett inputs 1-2 straight through Carla to outputs without plugins. Inside patchbay: system input 1-2 -> system output 1-2.

**Processed monitoring:** Route Scarlett inputs 1-2 through effects (e.g., amp sim) before output. Adds latency but lets you hear effects while playing.

**Separate dry + wet:** Send Scarlett to both loopers (dry recording) AND through Carla effects to monitors (wet monitoring). Loopers records dry signal; you hear processed.

## Launching Carla

Always use the dev script — it handles PipeWire quantum and buffer settings:

```bash
./dev run          # Start Carla with quantum 256
./dev run -q 512   # Custom quantum
```

Never launch Carla directly (`python3 source/frontend/carla.py`) — it won't set the PipeWire quantum and you'll get xruns.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Guessing port names | Always `pw-link -o` / `pw-link -i` first |
| Using `jack_connect` for external connections | Always use `pw-link` — `jack_connect` silently fails for Carla→Scarlett |
| Wrong loopers port names | It's `in_l`/`in_r` not `input_l`/`input_r` |
| Assuming plugin IDs | Always `list_loaded_plugins()` to check |
| Not checking existing connections | `pw-link -l` before connecting |
| Connecting without discovering new loop ports | Re-run `pw-link -o` after adding loops |
| Connecting system in 1-2 to new chain without disconnecting old | Always disconnect system 1-2 from previous chain first |
| Manually specifying mono/stereo for routing | Routing tools auto-detect now — just omit channel params |
| Building chains manually plugin-by-plugin | Use `build_effects_chain` for serial chains |
| Connecting `loopN_out_l` to both L and R inputs | Wire L→L, R→R to preserve panning from loopers |
