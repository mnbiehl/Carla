# Task 12 Report: `observe()` I/O builder + Carla-side `rig_handles` tool

## Status: DONE

## Commit
- `<see below>` — feat(rig): observe() I/O assembler and rig_handles observation tool

## What was done

Followed the brief's TDD steps exactly:

1. Verified the real shipped APIs before transcribing the brief's test, per
   instructions (this task touches shipped `controller.py`/`register.py` for
   the first time):
   - `RigController.__init__(self, graph, instance_manager, chain_launcher,
     jack_router, sleep=..., remote_factory=..., list_outputs=...,
     list_inputs=..., monitor_ports=..., plugin_db=...)` — matches the
     brief's assumed kwargs exactly.
   - `RigController._remote(node) -> RemoteInstance` — exists with that
     exact name (`controller.py:80`).
   - `RemoteInstance.list_handles(self) -> dict[int, str]` — exists with
     that exact name/shape (`remote.py:156`), already used the same way by
     the existing `_refresh_ids` method.
   - `graph.Node`, `graph.RigGraph`, `graph.RuntimeUnit` constructors match
     the brief's test fixture field-for-field.
   - `test_rig_register.py`'s real `EXPECTED_TOOLS` has **16** entries (not
     14 as its own stale docstring claims) and its own test names already
     say `test_all_16_tools_are_registered` / `test_tool_count_is_exactly_16`
     — consistent with the brief's "bump count 16→17".
2. Wrote `tests/test_rig_observe_io.py` verbatim from the brief.
3. Ran it and confirmed the expected failure: `ImportError: cannot import
   name 'observe' from 'carla_mcp.rig.observe'`.
4. Appended `observe()` to `rig/observe.py` verbatim from the brief, and
   `snapshot_handles` to `RigController` (after `import_rig_state`) verbatim
   from the brief.
5. Registered `rig_handles` in `register.py` before the probe-tools section,
   verbatim from the brief.
6. Updated `tests/test_rig_register.py`:
   - Added `"rig_handles"` to `EXPECTED_TOOLS`.
   - Added `controller.snapshot_handles = AsyncMock(return_value={"nodes":
     {}, "errors": []})` to `_make_mcp_and_controller`.
   - Bumped `test_all_16_tools_are_registered` → `test_all_17_tools_are_registered`
     and `test_tool_count_is_exactly_16` → `test_tool_count_is_exactly_17`
     (count 16→17), matching the brief.
   - **Extra fallout not named by the brief, adapted to reality**: the file
     also has a `TestProbeRegistration` class with two more tests that
     encode the base tool count — `test_probe_omitted_means_only_16_tools`
     (asserts `len(...) == 16`) and `test_probe_adds_three_tools` (asserts
     `len(registered) == 19`, i.e. 16 base + 3 probe). Since the real base
     count is now 17, these would fail without adjustment. Renamed/bumped
     them to `test_probe_omitted_means_only_17_tools` (17) and
     `test_probe_adds_three_tools` (20 = 17 + 3). Also bumped the module
     docstring's stale "14 tools" to "17 tools".
7. Ran the new test file + register test file: 23/23 passed.
8. Ran the full suite: 620 passed.
9. Committed with the brief's exact message.

## Recorded adaptations

1. **No API deviations** — unlike the task's stated risk, every real
   signature the brief's test assumed (`RigController` ctor kwargs,
   `_remote(node)`, `RemoteInstance.list_handles()`, `Node`/`RigGraph`/
   `RuntimeUnit`) matched the brief exactly. No implementation or test
   fixture changes were needed beyond the brief's own snippets.
2. **Test-count fallout beyond the two tests the brief named**: the brief
   said "bump count 16→17 in `test_all_16_tools_are_registered`/
   `test_tool_count_is_exactly_16`", but `test_rig_register.py` has two
   more tests (`test_probe_omitted_means_only_16_tools`,
   `test_probe_adds_three_tools`) that also hard-code the base-16 count.
   Left un-bumped, these would have failed after adding `rig_handles`.
   Adjusted both (16→17, 19→20) and renamed the first for consistency with
   the existing "count encoded in test name" convention. This is scope the
   brief's checklist missed, not a deviation from anything it specified.
3. Minor: fixed the module docstring's pre-existing stale "14 tools" →
   "17 tools" while touching the count in that file (cosmetic, no test
   impact — was already wrong at 14 vs the real 16 before this task).

No other deviations. `observe()`'s signature/behavior (per-callable
shielding, `Link` construction, handles dict copy) and `snapshot_handles`'s
behavior (track/bus-only iteration, per-node error collection, no raise)
match the brief's spec verbatim.

## Test summary

Full suite (`uv run python -m pytest source/frontend/carla_mcp/tests/ -v`):
**620 passed**, 10.55s. New file alone: 3 passed
(`test_assembles_snapshot_from_callables`, `test_probe_failures_never_raise`,
`test_collects_per_node_handles_and_errors`). `test_rig_register.py`: all
17 tests passed after the count bump.

## Concerns

- The brief's checklist for `test_rig_register.py` named only 2 of the 4
  tests actually affected by the tool-count bump; future tasks that touch
  `register.py` again should grep for hard-coded tool counts rather than
  trust the brief's enumerated test names.
- Pre-existing unrelated unstaged changes in the working tree
  (`.gitignore`, `.gitmodules`, `.mcp.json`, untracked `.env.example`) were
  left untouched and not included in this commit — they predate this task.
