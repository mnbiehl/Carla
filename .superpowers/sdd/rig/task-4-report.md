# Task 4 Report: `diff(graph, observed)` — pure diff engine

**Status:** DONE

**Commit:** `29b4a677a` — "feat(rig): pure diff engine over desired graph vs observed state"
(branch `feat/rig-reconciler`)

## What was done

Followed the brief's checkbox steps exactly, strict TDD:

1. Read `task-4-brief.md` and `global-constraints.md`.
2. Confirmed the file state matches the brief's assumptions: `rig/reconcile.py`
   already had `PortPair`, `Expansion`, `expand_edges`, `in_rig_port_space` from
   Task 3, and unused `Link`/`ObservedState` imports awaiting this task.
   Verified `RuntimeUnit`, `Node`, `Effect`, `ObservedState` field names/shapes
   in `rig/graph.py` and `rig/observe.py` line up with what the test fixture
   and implementation expect.
3. Wrote `source/frontend/carla_mcp/tests/test_rig_reconcile_diff.py` verbatim
   from the brief.
4. Ran it and confirmed the expected failure:
   `ImportError: cannot import name 'diff' from 'carla_mcp.rig.reconcile'`.
5. Appended `RigDiff` dataclass and `diff()` to `rig/reconcile.py`, verbatim
   from the brief (issues()/issue_count/is_clean/verdict, and the pure diff
   function consuming `expand_edges`, `in_rig_port_space`, `graph.runtime_units`,
   and `node.effects`/`observed.instance_handles` for unresolved-effects
   detection).
6. Ran `test_rig_reconcile_diff.py` + `test_rig_reconcile_expand.py` together:
   36 passed, no failures.
7. Ran the full suite: `573 passed in 10.47s`.
8. Committed exactly the two intended files
   (`rig/reconcile.py`, `tests/test_rig_reconcile_diff.py`) with the brief's
   exact commit message. Left pre-existing unrelated unstaged changes
   (`.gitignore`, `.gitmodules`, `.mcp.json`, `.env.example`, `.superpowers/`)
   untouched — none of those belong to this task.

## Adaptations

None. The brief's test and implementation code worked as-given with zero
modification — all interfaces (`RuntimeUnit`, `Node.effects`, `Effect.handle`,
`ObservedState.instance_handles`, `Expansion.absent_nodes/dead_ports/waitable_ports`)
matched exactly what Tasks 1-3 had already produced.

## Verification against global constraints

- No new third-party imports; `rig/reconcile.py` still only uses stdlib
  (`re`, `dataclasses`, `typing`).
- `diff()` is pure: no I/O, no subprocess, no clock — it only reads from
  the passed-in `graph`/`observed` and calls `expand_edges`/`in_rig_port_space`,
  which are themselves pure (Task 3).
- Verdict string format confirmed exact: `"OK"` when clean,
  `"DEGRADED: {n} issues"` otherwise (test `test_missing_connection_reported`
  asserts `"DEGRADED: 1 issues"` literally).
- `waitable_ports` correctly excluded from `issues()`/`issue_count` (mirrors
  dead ports/absent nodes for planning only, not counted as its own category).

## Test summary

Full suite: **573 passed**, 0 failed (`uv run python -m pytest
source/frontend/carla_mcp/tests -q`).
Task-4-scoped run: 36 passed (10 new diff tests + 26 pre-existing expand tests).

## Concerns

None. This was a clean, mechanical TDD pass — the brief's code was correct
and complete as written; no BLOCKED conditions encountered.
