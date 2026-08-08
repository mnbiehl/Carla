# Task 11 Report: Converge engine — verified `do_stop`

## Status: DONE

## Commit
- `5617aaea7` — feat(rig): verified do_stop teardown in reverse start order

## What was done

Followed the brief's TDD steps exactly:

1. Wrote `source/frontend/carla_mcp/tests/test_rig_converge_stop.py` verbatim from the brief.
2. Ran it and confirmed the expected failure: `ImportError: cannot import name 'do_stop' from 'carla_mcp.rig.converge'`.
3. Appended `DEFAULT_STOP_UNITS` and `do_stop` to `rig/converge.py`, with one recorded adaptation (below).
4. Ran the new test file: 3/3 passed.
5. Ran the full suite: 636 passed.
6. Committed with the brief's exact message.

## Recorded adaptation

The brief's proposed implementation sorted stop order via
`sorted(units, key=lambda u: (-UNIT_START_ORDER.get(u.kind, 9), u.name))` —
i.e. reusing `reconcile.UNIT_START_ORDER` negated. I verified this does
**not** produce the order the brief itself documents and the test asserts.

`UNIT_START_ORDER` (existing, from Task 1-10 `reconcile.py`):
`looper-engine=0, looper-mcp=1, a2j=2, carla-main=3, carla-child=4`.

Negating and sorting ascending gives: `carla-child, carla-main, a2j,
looper-mcp, looper-engine` — a2j lands third, right after carla-main.

But the brief's prose and `DEFAULT_STOP_UNITS` order, and the test's
assertion (`ops.stopped == ["carla:strat", "carla:main", "looper:mcp",
"looper:engine", "a2j"]`), all require a2j to stop **last**, after both
looper units.

So a straight negation of `UNIT_START_ORDER` is not the same relation as
the documented stop order — a2j's start-rank (2) sits between the looper
units (0, 1) and carla-main (3), so negating it doesn't reorder it to the
end.

Fix: added a small local `UNIT_STOP_ORDER` dict in `converge.py`
(`carla-child=0, carla-main=1, looper-mcp=2, looper-engine=3, a2j=4`)
and sorted on that instead of on negated `UNIT_START_ORDER`. This matches
the brief's documented order, `DEFAULT_STOP_UNITS`' order, and the test
exactly. `reconcile.UNIT_START_ORDER` itself was left untouched (still
used by `do_load`/`plan`), per the brief's file-scope (`converge.py`
append only).

No other deviations. `DEFAULT_STOP_UNITS`, `do_stop`'s signature/behavior
(graph vs. no-graph branch, verify-after-stop, DEGRADED reporting) match
the brief's spec verbatim.

## Test summary

Full suite (`uv run python -m pytest -q`): **636 passed**, 10.60s.
New file alone: 3 passed (`test_stops_in_reverse_start_order`,
`test_survivor_degrades_verdict`, `test_no_graph_uses_default_units`).

## Concerns

- The brief's own sample implementation snippet (step "Append to
  `rig/converge.py`") contains the same negated-`UNIT_START_ORDER` sort
  key that fails to reproduce the documented stop order — worth fixing
  the brief file upstream if other tasks (e.g. Task 14 bridge) copy that
  snippet again.
- Pre-existing unrelated unstaged changes in the working tree
  (`.gitignore`, `.gitmodules`, `.mcp.json`, untracked `.env.example`,
  `.superpowers/`) were left untouched and not included in this commit —
  they predate this task.
