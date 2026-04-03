---
name: rig-conductor
description: Use when managing the unified looper+Carla rig - routing loop outputs to effects chains, setting up for new instruments, session lifecycle (start/save/load), or asking about current rig state. Do NOT use for pure plugin parameter tweaking, pure looper operation (record/play/overdub), or audio engineering research with no rig context.
---

# Rig Conductor

Manage the unified loopers + Carla audio rig. Reason about what's connected to what and orchestrate multi-step transitions.

## Signal Flow (the one truth)

```
Scarlett → loopers (fixed, always)
loopers loop N outputs → Carla input pair → effects chain → Carla output → Scarlett monitors
```

Carla **never** sees the live Scarlett input. It only processes loop playback. Loopers handles its own monitoring internally.

## Core Concepts

| Concept | Definition |
|---------|-----------|
| **Loop** | A recorded loop in loopers. Named by the user with both instrument and role (e.g., "rhythm guitar 1", "lead bass", "pad synth"). The name carries semantic meaning. |
| **Chain** | An effects chain in Carla. Defaults to **one per loop**. May be shared between loops when they have similar names/roles and the user confirms. |
| **Assignment** | Which loop outputs route to which chain's Carla input pair. |
| **Rig** | The complete state: all chains, loops, assignments, and lifecycle status. |

## Defaults and Sharing Rules

- **Default: each loop gets its own chain.** Many effects (compressors, gates, anything level-dependent) don't work correctly with multiple sources summed together.
- **Sharing is the exception, not the rule.** When loops have clearly similar names (e.g., "rhythm guitar 1" and "rhythm guitar 2"), Claude may *suggest* sharing but must confirm with the user first.
- **When sharing, only share safely.** Per the `carla-effects-chains` skill: dynamics processors (compressor, gate, expander) must be per-source. Linear/time-based effects (EQ, reverb, delay, chorus) can be shared. In practice this means shared chains need per-loop compressors feeding into a shared EQ/reverb tail.
- **Carla input pairs are allocated per chain:** first chain = inputs 3-4, second = 5-6, etc. Follow the input mapping convention in the `audio-routing-workflow` skill.
- **Scarlett inputs 1-2 inside Carla are unused.** Scarlett connects directly to loopers, not Carla.

## State Discovery Protocol

**On first interaction in a session:** Build the full rig mental model before doing anything.

1. `get_rig_status` — are Carla and loopers running?
2. `list_loaded_plugins` — what chains exist in Carla?
3. `list_patchbay_connections` — what's routed to what inside Carla?
4. `pw-link -l` — what JACK connections exist between apps?

Report a concise summary: "Carla has 3 chains: rhythm guitar (plugins 0-2, inputs 3-4), lead guitar (plugins 3-5, inputs 5-6), bass (plugins 6-8, inputs 7-8). Loop 0 'rhythm guitar 1' → rhythm guitar chain, loop 1 'lead guitar' → lead guitar chain, loop 2 'bass groove' → bass chain."

**After initial discovery:** Trust the known state. Only re-probe if an operation fails or the user reports something unexpected.

## Operational Sequences

### Start a session
1. `start_rig` — one call starts everything: Carla engine + carla-control GUI, loopers engine + MCP, and creates all pw-link connections (Scarlett↔Carla, Scarlett→loopers)
2. Or for resuming: `load_rig_session(name)` then `start_rig`
3. Run the state discovery protocol above
4. Report rig state to user

**Note:** `carla_start` launches `carla-control` (a GUI viewer), not `carla.py`. The bridge's engine is the real engine. `looper_start` launches both the `loopers` Rust binary AND the MCP server.

### Route a loop to a new chain
1. Discover the loop's output ports: `pw-link -o | grep "^loopers:loopN"`
2. Allocate the next available Carla input pair
3. **Delegate chain building to the effects-chain-builder agent** — pass the loop name, instrument type, and any user preferences about desired sound
4. Connect loop outputs to the chain's input pair: `pw-link "loopers:loopN_out_l" "Carla:audio-inX"`
5. Verify with `pw-link -l`
6. Update the mental model

### Route a loop to an existing chain (sharing)
1. Confirm with user that sharing is intended
2. Connect loop outputs to the shared chain's existing input pair (sources sum at the input)
3. Warn if the chain has dynamics processors — those will react to the combined signal
4. Verify and update mental model

### Switch what chain a loop goes through
1. Disconnect the loop from its current chain's input pair (`pw-link -d`)
2. Connect the loop to the new chain's input pair
3. Verify
4. Update the mental model
5. If the old chain has no more loops routed to it, ask if user wants to remove it

### Save a session
1. `save_rig_session(name)` — captures Carla + looper state + routing

## When to Delegate

| Task | Delegate to | Context to pass |
|------|------------|-----------------|
| "What plugins for a warm jazz tone?" | effects-chain-builder agent | Instrument type, desired character |
| "Build me a vocal chain with de-essing" | effects-chain-builder agent | Instrument type, requirements, allocated input pair |
| "Check all my levels" | effects-chain-builder agent | Current chain topology, plugin IDs |
| "What should the compressor ratio be?" | effects-chain-builder agent | Instrument type, musical context |
| Any JACK port connection or Carla patchbay routing | Do it yourself | Use `audio-routing-workflow` skill knowledge |

**Rule:** The conductor handles routing, state, and orchestration. Audio engineering decisions go to the effects-chain-builder agent.

## Interpreting User Intent

| User says | Claude does |
|-----------|------------|
| "Set up for guitar" | Ask what kind of sound they want, then delegate chain building to the agent. |
| "I just recorded loop 2, it's rhythm guitar" | Create a new chain for it (default). Route loop 2 to the new chain. |
| "Loop 3 is also rhythm guitar" | Note the similar name. Ask: "Loop 0 is also rhythm guitar — should loop 3 share its chain, or get its own?" |
| "Route loop 2 through the bass chain" | Execute the routing sequence. |
| "Switch loop 0 to a different sound" | Ask what they want, build a new chain, reroute. |
| "What's connected right now?" | Report from the mental model. Re-probe if stale. |
| "Start fresh" | Start backends, run discovery, report. |
| "Save this" | `save_rig_session` with a descriptive name. |

## Inferring from Loop Names

Loop names carry meaning. Use them to:
- **Identify instrument type** for chain building: "rhythm guitar 1" → guitar effects, "fingerpicked bass" → bass effects
- **Detect potential sharing**: similar prefixes ("rhythm guitar 1", "rhythm guitar 2") suggest related parts
- **Never assume sharing** — always ask. "These sound related — same chain or separate?"

## Reference Skills

- **`audio-routing-workflow`** — JACK port discovery (`pw-jack` commands), Carla patchbay routing syntax, input mapping convention, common mistakes to avoid
- **`carla-effects-chains`** — Per-source vs shared plugin decisions, chain topology patterns, tested plugin choices

## Iron Rule: Hands Off the Transport

**NEVER run any looper transport or recording commands** (record, play, stop, overdub, undo, redo, clear, transport_start, transport_stop, etc.) **unless the user explicitly asks.** The musician controls when recording starts and stops. Claude handles routing, effects, and configuration only. If you need a test loop for gain staging, ASK the user to record one.

## Key Gotchas

- **Carla in patchbay mode has NO audio passthrough.** Without plugins loaded and connected internally (system in → plugin → system out), no audio flows through Carla — the user hears silence. After `start_rig`, external connections (Scarlett↔Carla) exist but internal Carla routing is empty. Audio only flows once `build_effects_chain` or manual patchbay connections create an internal signal path.
- **Always wire loops stereo: L→L, R→R.** Connect `loopN_out_l` to the chain's left input and `loopN_out_r` to the right input. This preserves panning from loopers. Never duplicate L to both channels.
- **Plugin IDs shift when plugins are added/removed.** Always `list_loaded_plugins` after modifying chains.
- **Dynamic ports.** Loopers creates `loopN_out_l/r` ports when loops are recorded. Always re-discover ports after new loops appear.
- **Mono plugins collapse stereo.** Use stereo plugin variants (e.g., "x42-comp Stereo" not "C* Compress") when processing stereo-panned loops.
