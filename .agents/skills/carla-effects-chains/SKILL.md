---
name: carla-effects-chains
description: Use when designing or building multi-plugin effects chains in Carla, choosing which plugins to share vs separate per source, or making audio engineering decisions about signal flow topology.
---

# Carla Effects Chains

## Overview

Design effects chains with proper signal flow topology. The key decision is which plugins process each source independently vs which are shared across sources.

## Per-Source vs Shared Plugins

| Plugin Type | Per-Source or Shared | Why |
|-------------|---------------------|-----|
| Compressor | **Per-source** | Reacts to signal level — a loud hit on one source ducks the others |
| Gate/Expander | **Per-source** | Threshold is source-dependent |
| EQ | **Shared OK** | Linear processing, sources sum cleanly |
| Reverb | **Shared OK** | Same space for all sources sounds natural |
| Delay | **Shared OK** | Time-based, works on summed signal |
| Chorus/Flanger | **Shared OK** | Modulation effects work on summed signal |
| Limiter | **Shared (on master)** | Protects output, should see full mix |

**Rule of thumb:** If the plugin's behavior depends on signal level (dynamics processors), it needs to be per-source. If it's linear or time-based, sharing is fine.

## Signal Flow Pattern

```
Source A → Comp A ─┐
Source B → Comp B ─┼→ Shared EQ → Shared Reverb → Output
Source C → Comp C ─┘
```

Multiple sources summing into a shared plugin input is standard mixing — Carla handles this correctly.

## Shared Reverb: Add Parallel Per-Source Dry Gains

A shared reverb is the right call (one space for all sources), but routing every
source *through* it in series means the only dry blend you have is the reverb's own
global dry/wet — you can no longer ride one instrument louder/quieter in the dry mix.
Fix this by splitting dry and wet into **parallel** paths and giving each source its
own dry-gain plugin:

```
Source A → Comp A → EQ A ─┬─→ Dry Gain A (Gain 2x2) ─┐
Source B → Comp B → EQ B ─┼─→ Dry Gain B (Gain 2x2) ─┼─→ Output
Source C → Comp C → EQ C ─┼─→ Dry Gain C (Gain 2x2) ─┤
                          └─────→ Shared Reverb ──────┘   (fed by sum of all sources)
```

Each source fans out to (a) its own stereo `Gain 2x2` passthrough — the per-source
**dry** fader — and (b) the shared reverb send. All dry gains and the reverb output
sum to the master. Now every instrument's dry level *and* the shared wet return are
adjustable from one instance.

**Rule of thumb:** Any time a reverb (or other wet effect) is shared across sources,
add one parallel stereo gain per source for independent dry control. Without it,
"make the uke louder but keep the same room" has nowhere to live.

**Convolution caveat:** Convolution IRs load only via `carla_set_plugin_file` on the
**main** Carla instance, not on child track instances — so a convolution reverb must
be the shared room on main, which makes the parallel dry-gain pattern mandatory there.

**Watch-outs (learned in practice):**
- Adding plugins to the main instance can silently **drop** existing hardware-output
  links (`Carla:audio-out*` → interface, metronome → interface). Re-verify and
  restore them after inserting the dry-gain plugins.
- A convolution wet return can clip — trim the convolver's Output Gain (≈ −20 dB for
  convoLV2), not the dry gains.

## Building a Chain

**Preferred: Use `build_effects_chain` for simple serial chains:**

```python
# Single call builds and wires a complete chain
build_effects_chain(
    plugins=["LSP Gate Mono", "LSP Para EQ x16 Mono", "LSP Compressor Mono", "Dragonfly Plate Reverb"],
    connect_system_input=True,
    connect_system_output=True
)
```

This auto-detects mono/stereo per plugin and wires them correctly (mono→mono, mono→stereo duplicate, stereo→mono sum, stereo→stereo L/R).

**For complex topologies (multiple sources into shared plugins), use manual routing:**

```python
# 1. Load per-source compressors
add_plugin_by_name("x42-comp - Dynamic Compressor Stereo")  # plugin 0 - source A
add_plugin_by_name("x42-comp - Dynamic Compressor Stereo")  # plugin 1 - source B

# 2. Load shared plugins
add_plugin_by_name("x42-eq - Parametric Equalizer Stereo")  # plugin 2 - shared
add_plugin_by_name("Dragonfly Room Reverb")                  # plugin 3 - shared

# 3. Wire: comps → EQ → reverb (auto-detects mono/stereo)
connect_plugins(0, 2)  # comp A → EQ
connect_plugins(1, 2)  # comp B → EQ
connect_plugins(2, 3)  # EQ → reverb

# 4. Wire system I/O
connect_system_to_plugin(system_input=1, plugin_id=0)  # source A (auto-detect channels)
connect_system_to_plugin(system_input=3, plugin_id=1)  # source B
connect_plugin_to_system(plugin_id=3, system_output_left=1)  # reverb → out
```

**Parameter snapshots** preserve tuning across chain rebuilds:

```python
save_plugin_snapshot(plugin_id=0, name="my-comp-settings")
# Later, after rebuilding:
load_plugin_snapshot(plugin_id=0, name="my-comp-settings")
```

## Tested Plugin Choices

| Role | Plugin | Notes |
|------|--------|-------|
| Compressor | x42-comp - Dynamic Compressor Stereo | Clean, transparent |
| Parametric EQ | x42-eq - Parametric Equalizer Stereo | Surgical, low CPU |
| Room Reverb | Dragonfly Room Reverb | Natural room sound |

## Acoustic Guitar (SM58 Beta)

For bright, punchy concert guitar through a dynamic mic:
- **EQ:** Cut low mud (80-120Hz), tame harshness (2-4kHz), gentle air boost (10kHz+)
- **Compressor:** Light ratio (2:1-3:1), slow attack to preserve transients
- **Reverb:** Small room, short decay, low mix (10-20%) for live performance
