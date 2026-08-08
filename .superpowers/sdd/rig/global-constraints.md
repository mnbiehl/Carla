## Global Constraints

- Everything importable from Carla-runtime code (`carla_mcp/rig/*`, `carla_mcp/utils/*`) is stdlib-only — see kb tech-debt `system-python-user-site-dependency-fragility-constrains-carl.md`; JSON, `dataclasses`, `re`, `subprocess`, `asyncio` only. No new third-party imports in `rig/`.
- Always `pw-link` (via `JackRouter` / `utils/pw_link.py`), never `jack_connect`.
- Clean-slate before restoring routing: every load disconnects all rig-port-space links (`loopers:*`↔`Carla*`, `Carla*`↔hardware, MIDI into `loopers:loopers_midi_in`) before replaying desired edges — this is the only defense against PipeWire persistent-link restoration.
- Address everything by stable name (node names, handles, port names), never by volatile numeric id; looper loops are addressed as `loop:<port_index>` with the engine `looper_id` carried as data.
- Verify before reporting success: every mutating tool re-observes and re-diffs before it prints its verdict; `save_rig_session` re-reads its own output and stats every referenced file.
- Loops and all stereo pairs wire L→L, R→R (2×2 straight, 1→2 mono fan-out, 2→1 sum) — the exact `_make_port_pairs` rules already in `rig/controller.py`.
- Reports are the contract: every tool report opens with `OK` / `DEGRADED: <n> issues` / `FAILED: <reason>`, and every skipped, failed, or unliftable item is named in the report. Nothing silently dropped.
- The diff engine (`rig/reconcile.py`) is pure — no I/O, no subprocess, no clock — and is the primary unit-test surface.
- Tests run with `uv run pytest <path> -v` from the repo root (`/home/michael/roboloops/carla-mcp-fork`).

