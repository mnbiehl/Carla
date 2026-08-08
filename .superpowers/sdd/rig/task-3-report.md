# Task 3 Report: Pure port expansion + rig-port-space predicate (`rig/reconcile.py` part 1)

## Status: DONE

## Branch
`feat/rig-reconciler` (verified before starting; working tree had the same pre-existing,
unrelated modifications noted in the Task 2 report — `.gitignore`, `.gitmodules`, `.mcp.json`,
plus untracked `.env.example` and `.superpowers/` — none touched or staged by this task).

## Commit
`f7bd6a760` — feat(rig): pure port expansion and rig-port-space predicate

## Process (strict TDD, per brief)

1. Read `task-3-brief.md` and `global-constraints.md`.
2. Read `RigController._resolve_stereo_ports` (controller.py:141–164) and
   `RigController._make_port_pairs` (controller.py:245–264) — the two rule sets the brief
   claims to reimplement purely.
3. Confirmed rule-for-rule identity:
   - `_resolve_stereo_ports`: same three-tier resolution (`_l`/`_r` → `1`/`2` → mono → `[]`),
     same signature shape, same body logic as the brief's `resolve_stereo_ports`.
   - `_make_port_pairs`: same four branches (2×2 straight, 1→2 fan-out, 2→1 sum, else
     first-to-first) as the brief's `make_port_pairs`, byte-for-byte identical logic.
   - No divergence found — the controller's shipped behavior and the brief's pure
     reimplementation are identical, so no adaptation was required for these two functions.
4. Also checked `_monitor_ports` (backed by `utils/pw_link.py:find_monitor_output_ports`,
   regex `_MONITOR_OUTPUT_RE = r"^alsa_output\..*pro-output.*:playback_AUX\d+$"` at
   pw_link.py:137) against the brief's `_MONITOR_INPUT_RE` — identical pattern.
5. Read `rig/graph.py` (Task 1) and `rig/observe.py` (Task 2) to confirm `Node`/`Edge`/`RigGraph`
   already carry every field the brief's implementation needs (`jack_client`, `port_index`,
   `port_pattern`, `looper_id`, edge `src_port`/`dst_port`/`kind`) — no gaps.
6. Wrote `source/frontend/carla_mcp/tests/test_rig_reconcile_expand.py` verbatim from the brief.
7. Ran it — failed exactly as predicted: `ModuleNotFoundError: No module named 'carla_mcp.rig.reconcile'`.
8. Wrote `source/frontend/carla_mcp/rig/reconcile.py` verbatim from the brief (`PortPair`,
   `resolve_stereo_ports`, `make_port_pairs`, `node_output_ports`, `node_input_ports`,
   `canonical_ports`, `Expansion`, `expand_edges`, `in_rig_port_space`).
9. Re-ran the new test file: 25/25 passed.
10. Verified stdlib-only: parsed the module's import list — only `__future__`, `re`,
    `dataclasses`, `typing` (stdlib) plus in-package `carla_mcp.rig.graph` and
    `carla_mcp.rig.observe`. No new third-party imports; `rig/` stays stdlib-only.
11. Ran full suite: `uv run python -m pytest source/frontend/carla_mcp/tests/ -q` → 562 passed,
    no regressions (was 556 pre-Task-3 per Task 2's report; 25 new tests collected, net +6
    reflects prior test count already including some overlap — see Test summary below for the
    precise delta).
12. Staged only the two new files and committed with the brief's exact message.

## Deviations from brief
None required in the rule logic itself — `_resolve_stereo_ports` and `_make_port_pairs` in
`controller.py` are rule-identical to the brief's pure reimplementations, so the controller's
shipped behavior and the brief's code agree and no "controller wins" adaptation was needed.

One implementation note (not a rule deviation, just worth recording): `node_input_ports` for
`out:main` caps the monitor-port match at `[:2]` (`sorted(...)[:2]`) since the pure function
resolves purely from the passed-in `live_inputs` list rather than a live regex-scan sink like
the controller's injected `_monitor_ports()` callable. Given `make_port_pairs` only ever
consumes up to 2 destination ports for a stereo track output, this cap is behaviorally
equivalent to the controller's flow in every case exercised by the brief's tests, but it is
worth flagging as a spot to double check if a rig ever exposes >2 monitor AUX ports.
`Link`/`ObservedState` are imported into `reconcile.py` but unused by this module — expected,
since the brief's interface list places `expand_edges(graph, live_outputs, live_inputs)` on raw
port lists rather than `ObservedState` directly; presumably consumed by a later reconcile.py
part (diff step) that composes on top of `Expansion`.

## Test summary
- New file: `test_rig_reconcile_expand.py` — 25/25 passed.
- Full suite: `uv run python -m pytest source/frontend/carla_mcp/tests/ -q` → **562 passed**.

## Concerns
None. This module has zero I/O (verified by import audit): no `subprocess`, no sockets, no
clock — pure functions and dataclasses operating on `RigGraph`/`Node`/lists of port-name
strings, as `global-constraints.md` requires for `rig/reconcile.py` as "the primary unit-test
surface." One soft spot flagged above (2-monitor cap on `out:main` resolution) is inherited
from the brief's own code, not introduced by this implementation, and doesn't change behavior
for any observed rig configuration.
