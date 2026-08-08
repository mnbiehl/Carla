# Task 10 Report: self-verifying `do_save` with live-link lifting

**Status:** DONE
**Branch:** feat/rig-reconciler (verified before commit)
**Commit:** 82df51609 — `feat(rig): self-verifying do_save with live rig-space link lifting`

## What was done (strict TDD)

1. Wrote failing test `source/frontend/carla_mcp/tests/test_rig_converge_save.py` (5 tests, verbatim from brief).
2. Ran it: confirmed `ImportError: cannot import name 'do_save'`.
3. Appended to `source/frontend/carla_mcp/rig/converge.py`:
   - `_LOOP_PORT_RE`, `_graph_from_export`, `_lift_link`, `do_save` (exact brief code).
   - Top-of-file `import re`.
4. Ran the target file: 5 passed.
5. Ran full `carla_mcp/tests/` suite: 613 passed.
6. Committed with the brief's exact message.

## Recorded adaptations (minimal)

- **`LOOPER_MIDI_IN` import.** The brief's step note said "`LOOPER_MIDI_IN` comes from `reconcile`, already imported." It was defined in `reconcile.py` (line 18) but was NOT in converge.py's existing `from carla_mcp.rig.reconcile import (...)` list. Added `LOOPER_MIDI_IN` to that import group. No other change; the constant value is unchanged. This is the only deviation from "code is exact as written" and it was required for the brief's own `_lift_link` code to run.

Everything else (delegation to `session._lift_rig_state` via the private in-function import — NOT forked, per watchpoints; fakes returning the unwrapped GetState dict with top-level `main_muted`/`all_muted`/`loopers`; self-verify via `read_session` + `verify_session_files`) matched the brief exactly.

## Verification

- Target file: 5/5 passed.
- Full suite: `uv run python -m pytest source/frontend/carla_mcp/tests/ -q` → **613 passed in 10.54s**.
- Self-verification path exercised by tests: OK verdict (`test_save_emits_verified_v3`), DEGRADED on missing referenced file (`test_missing_referenced_file_degrades`), FAILED when nothing running (`test_nothing_running_is_failed`), covered links not double-lifted (`test_loop_edge_normalized_not_duplicated`), capture+midi lift + a2j runtime unit (`test_capture_and_midi_links_lifted`).

## Concerns

- `return f"FAILED: nothing to save (carla and looper both unreachable)"` is an f-string with no interpolation (would trip ruff F541 if that rule is on). Kept verbatim per brief; harmless at runtime.
- Watchpoint reminder for downstream: the Rust `GetState` reply nests under a `"state"` key; `BridgeOps.looper_get_state`/`LooperClient.get_state()` must unwrap the envelope so `do_save` sees top-level `main_muted`/`loopers` (fakes already return unwrapped). To be verified in Task 14.

## Fix report (post-review finding, 2026-07-23)

**Finding:** `do_save`'s looper section iterated `loop_nodes_from_looper_state(state)`,
which silently skips any `state["loopers"]` entry lacking `port_index` (see its
docstring: "callers report that as degraded"). `do_save` never compared counts, so a
skipped looper track vanished from the saved session while the report said `OK` —
violating the project's global "nothing silently dropped" constraint.

**Fix (minimal, TDD):**
1. Added a failing test to `test_rig_converge_save.py`:
   `test_looper_without_port_index_is_named_not_silently_dropped` — a `DegradedLooperOps`
   subclass of `SaveFakeOps` whose `looper_get_state` appends a second entry
   (`id=99, port_index=None`) to the existing good entry (`id=7, port_index=0`). Ran it
   and confirmed it failed (`report == "OK"` instead of `DEGRADED:`), reproducing the bug.
2. Fixed `do_save` in `source/frontend/carla_mcp/rig/converge.py`: computed
   `raw_loopers`/`loop_nodes` once, and when `len(loop_nodes) < len(raw_loopers)`,
   appended one note per entry with `port_index is None`
   (`f"looper id={entry.get('id')} has no port_index (pre-contract engine?); dropped
   from saved session"`) before the existing `for loop_node in loop_nodes:` loop. Notes
   flow into the existing `issues = problems + notes` → `DEGRADED` verdict path; no
   other behavior changed.
3. Re-ran the new test: passed (report starts with `DEGRADED:`, names `id=99`, and
   `loop:0` — the good entry — is still present in the saved/reread session).

**Verification:**
- Covering tests: `uv run python -m pytest source/frontend/carla_mcp/tests/test_rig_converge_save.py source/frontend/carla_mcp/tests/test_rig_converge_load.py source/frontend/carla_mcp/tests/test_rig_observe_model.py -v` → **20 passed**.
- Full suite: `uv run python -m pytest -q` → **633 passed in 10.58s**.

**Commit:** `80e3b23ca` — `fix(rig): name port_index-less loopers dropped from saves (nothing silently dropped)`
