# Task 9 Report: Converge engine — `do_load`

**Verdict: DONE.** Clean-slate → converge → verify-with-one-retry implemented exactly per brief. All tests pass, full suite green, committed.

## What was done

Followed strict TDD:

1. **Wrote the failing test** `source/frontend/carla_mcp/tests/test_rig_converge_load.py` verbatim from the brief.
2. **Confirmed failure**: `ImportError: cannot import name 'do_load'` — as the brief predicted.
3. **Appended to** `source/frontend/carla_mcp/rig/converge.py` the three functions:
   - `rig_state_for_import(graph, session_dir) -> dict` — builds an `import_rig_state` v1 payload with **`edges=[]`** (converge owns ALL wiring; RigController must not race it — per watchpoints.md). Translates `loop:N` track sources to the `loopers:loopN_out` endpoint base, synthesizes endpoint nodes for those bases, and absolutizes `chain_file` against the session dir. Only `endpoint`/`track`/`bus` nodes are emitted (loop/app/midi are not Carla-land nodes).
   - `_apply_action(action, graph, ops, notes)` — executes one plan action (start_unit / wait_ports / disconnect / connect), recording every failure by name in `notes` (nothing silently dropped).
   - `do_load(name, session_dir, ops) -> str` — the load sequence: read/migrate (`FAILED:` on `SessionError`) → start down units in `UNIT_START_ORDER` → clean-slate all rig-space links (the PipeWire persistent-link defense) → payload (carla project, `import_rig_state` with edges=[], looper `LoadSession`, `set_looper_mutes`) → wait canonical ports → connect missing expanded pairs → verify with ONE `plan()` retry round → verdict-first `render_report` including migration notes (seeded from `sess.notes`).

## Verification

- Task-9 tests: **5 passed** (`test_rig_converge_load.py`).
- Full `carla_mcp` suite: **608 passed** in 10.64s — no regressions.

## Adaptations

**None.** The brief's code was transcribed exactly; all names it references were already imported in converge.py (staged in Task 8) and all graph/session/reconcile attributes it uses (`sess.notes`, `Effect.plugin`, `Node.main_muted/all_muted/port_index/chain_file`, `RigDiff.verdict/is_clean/issues`, `expand_edges`, `canonical_ports`, `plan`) exist as required.

## Constraint compliance

- stdlib-only: no new third-party imports.
- Clean-slate before restoring routing (global-constraints.md §clean-slate).
- Verdict-first reports; every failure named in notes (global-constraints.md §reports-are-the-contract).
- `rig_state_for_import` passes `edges=[]` (watchpoints.md).

## Commit

`03439fa1618797e75cf51bf619dfb714d089003a` on branch `feat/rig-reconciler`.

## Concerns

None blocking. Note the two `.py` files were staged individually per the brief; pre-existing unstaged repo-config changes (`.gitignore`, `.gitmodules`, `.mcp.json`, `.env.example`, `.superpowers/`) were left untouched.
