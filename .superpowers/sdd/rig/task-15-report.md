# Task 15 Report: Integration round-trip test

## Status: DONE

## Commit
- `e1179c44b` — test(rig): round-trip integration — save, reset, pollute, load, verify OK

No engine fix was needed; no separate commit required.

## What was done
- Read `task-15-brief.md` and `global-constraints.md` in full before touching code.
- Verified branch (`feat/rig-reconciler`) and confirmed the working tree had no
  conflicting local changes to the target file (it didn't exist yet).
- Cross-checked the brief's exact test code against the real implementations
  it imports from (`carla_mcp/rig/converge.py`'s `RigOps`, `do_load`,
  `do_routing_reset`, `do_save`, `do_verify`; `carla_mcp/rig/observe.py`'s
  `Link`/`ObservedState`; `carla_mcp/rig/session.py`'s `read_session`) to make
  sure signatures and semantics matched before transcribing — they did.
- Created `source/frontend/carla_mcp/tests/test_rig_roundtrip_integration.py`
  as a verbatim transcription of the brief's code block. No deviations from
  the brief were made.
- Ran the new test file alone: both tests passed on the first try
  (`test_save_reset_load_verify_is_ok`, `test_round_trip_survives_full_process_restart`).
  Per the brief's stated rule, since it passed immediately, Tasks 6–11 (the
  converge engine) are confirmed correct for this scenario — no debugging or
  engine changes were necessary.
- Ran the full suite: `uv run python -m pytest` → **651 passed**, 0 failed,
  27.24s.
- Staged only the new test file (`git add` by explicit path, not `-A`/`.`) —
  confirmed via `git status --short` that unrelated pre-existing changes
  (`.gitignore`, `.gitmodules`, `.mcp.json`, `.env.example`, `.superpowers/`)
  were left untouched.
- Committed with the brief's exact commit message.

## Deviations from the brief
None. Test code, commit message, and test-run commands all match the brief
verbatim.

## Notes on the "port_index-less loopers" nuance
The brief's context flagged that Task 10's `do_save` gained a note for
looper entries with no `port_index` (see `converge.py` lines ~330-338 and
`observe.py`'s `loop_nodes_from_looper_state`, which skips entries where
`port_index is None`). The fake's single looper entry (`id=7,
port_index=0, ...`) always carries a `port_index`, so this path is never
exercised by this test — consistent with the "no interaction expected"
prediction in the task context.

## Test results
- New file alone: 2 passed, 0.05s.
- Full suite: 651 passed, 27.24s, 0 failed.

## Concerns
None. The converge stack (Tasks 6-11) handled both the "seeded stale
crossed-link" scenario and the "full cold-world restart" scenario correctly
on the first run, with no engine changes required.

## Addendum: clean-slate ordering pin (2026-07-23)

### Why
A review of this file's original two tests found their stale-link
assertions check only *end state* (is the stale link gone, is the desired
wiring back), never *when* it was cleared. `do_load`'s step-6 retry pass
(`converge.py`) independently disconnects any link the diff still flags as
extra, so deleting `do_load`'s step-2 clean-slate loop entirely still makes
both existing tests pass — the retry pass silently covers for it. This
left the 2026-04-10 regression retro's specific follow-up
(`test_load_rig_clears_stale_links_before_restore`, i.e. "clean-slate must
be pinned, not just implied by convergence") unaddressed.

### What was added
- `OrderRecordingOps(RoundTripOps)`: a fake-world subclass that appends
  `("connect", src, dst)` / `("disconnect", src, dst)` tuples to
  `self.events` on every call, before delegating to the real fake logic.
- `TestCleanSlateOrdering.test_load_clears_stale_links_before_any_connect`:
  - `do_save` a rig, then `do_routing_reset` to wipe all rig-space links
    (forcing `do_load` to genuinely reconnect everything, so the test
    can't be trivially satisfied by "nothing needed reconnecting").
  - Seed the stale crossed link
    `("loopers:loop0_out_r", "CarlaChain_strat:audio-in1")`.
  - Clear `ops.events`, run `do_load`, assert report is `OK`.
  - Assert the stale link's disconnect event is present.
  - **The pin**: assert the stale-link disconnect's index in `events` is
    strictly before the index of the *first* connect event — i.e.
    clean-slate (step 2) ran before any wiring (step 5), not as a
    byproduct of the step-6 retry (which runs after step 5).

### Negative control (as requested)
1. Commented out `do_load`'s step-2 clean-slate loop in `converge.py`
   (the `observed = await ops.observe(graph)` + disconnect loop right
   after the "Clean slate" comment).
2. Ran the new test alone: **FAILED**, as expected — with clean-slate
   disabled, `do_routing_reset` still wiped all links beforehand, so
   step 5 issued every connect first (index 0), and the stale link's
   removal only happened via the step-6 retry pass *after* those
   connects (index 7). Assertion error:
   `clean-slate disconnect must happen before any connect (disconnect at
   7, first connect at 0)`.
2b. Note: an earlier draft of the test (without the `do_routing_reset`
    step) gave a false-negative-adjacent failure — with the previously
    correct wiring left undisturbed, `do_load` had literally nothing left
    to connect, so the negative-control run produced *zero* connect
    events rather than a wrongly-ordered one, tripping a guard assertion
    instead of the real ordering check. Adding `do_routing_reset` before
    seeding the stale link forces genuine reconnection work regardless of
    whether clean-slate runs, so the ordering assertion is the actual
    differentiator.
3. Restored the clean-slate block verbatim (confirmed via
   `git diff --stat converge.py` showing no diff).
4. Re-ran the new test alone: **PASSED**.
5. Ran the full file (`-v`): all 3 tests passed.
6. Ran the full suite (`uv run python -m pytest -q`): **652 passed**
   (651 prior + 1 new), 0 failed, ~27s.

### Commit
- `test(rig): pin clean-slate ordering — stale links cleared before any
  connect` (see git log for hash).

### Files touched
- `source/frontend/carla_mcp/tests/test_rig_roundtrip_integration.py`
  (appended `OrderRecordingOps` + `TestCleanSlateOrdering`).
- `converge.py` was touched only transiently for the negative control and
  is unchanged in the final commit.
