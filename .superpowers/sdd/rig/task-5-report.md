# Task 5 Report: `plan(diff)` + `render_report`

## Status: DONE

## What was done

Followed the brief exactly, strict TDD:

1. Read `task-5-brief.md` and `global-constraints.md`.
2. Read the current `rig/reconcile.py` (post Tasks 1-4: graph v3, `ObservedState`,
   `expand_edges`, `diff()`) and `rig/graph.py`'s `RuntimeUnit` dataclass to confirm
   `kind` values (`"carla-main" | "carla-child" | "looper-engine" | "looper-mcp" | "a2j"`)
   line up with `UNIT_START_ORDER` keys.
3. Wrote `source/frontend/carla_mcp/tests/test_rig_reconcile_plan.py` verbatim from the
   brief (8 tests: 6 for `plan()` ordering/dedup/unknown-unit behavior, 2 for
   `render_report` verdict-first / empty-section-omission).
4. Ran the new test file — confirmed the expected failure:
   `ImportError: cannot import name 'Action' from 'carla_mcp.rig.reconcile'`.
5. Appended to `rig/reconcile.py` verbatim from the brief: `UNIT_START_ORDER` dict,
   frozen `Action` dataclass, `plan(d, graph)`, `render_report(verdict, sections)`.
   No changes needed to the brief's code — it matched the existing module's imports
   (`dataclass`, `Optional`, `Tuple`, `List` already imported) with zero new imports.
6. Ran the new test file — all 8 pass.
7. Ran the full `carla_mcp` test suite — all 581 tests pass (no regressions in tasks
   1-4's tests or anywhere else).
8. Committed both files with the brief's exact commit message.

## Adaptations from the brief

None. The brief's code pasted in unmodified; the test file was copied unmodified.
No import changes, no signature changes, no additional stdlib imports.

## Constraint compliance (global-constraints.md)

- `rig/reconcile.py` remains stdlib-only (only pre-existing imports:
  `dataclasses`, `re`, `typing`) — no new third-party imports added.
- `plan()` and `render_report()` are pure — no I/O, no subprocess, no clock.
- Ordering guarantee verified by test: all `start_unit` (sorted by
  `UNIT_START_ORDER` rank then name) → single deduped/sorted `wait_ports` →
  all `disconnect` → all `connect`.
- Unknown down units (absent from `graph.runtime_units`) still get a
  `start_unit` action (rank 9 fallback), per
  `test_unknown_down_unit_still_yields_action`.

## Commit

`d557791be` — "feat(rig): plan() ordered fix actions and verdict-first report renderer"
(branch `feat/rig-reconciler`)

Files changed: `source/frontend/carla_mcp/rig/reconcile.py` (+64 lines appended),
`source/frontend/carla_mcp/tests/test_rig_reconcile_plan.py` (new, 65 lines).

## Test summary

Full suite: `uv run python -m pytest source/frontend/carla_mcp -v` → **581 passed**
(8 new for this task, 573 pre-existing, 0 failures).

## Concerns

None. Task 5 is self-contained and the brief's code required no adaptation.
