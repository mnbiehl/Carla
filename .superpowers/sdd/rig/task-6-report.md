# Task 6 Report — Manifest v3: `RigSession` read/write + self-verification

## Status: DONE

Branch: `feat/rig-reconciler` (verified correct branch before starting).

## Steps followed (strict TDD, per brief)

1. Read `task-6-brief.md` and `global-constraints.md` in full before touching code.
2. Checked the actual `Effect` / `Node` / `RuntimeUnit` dataclasses in
   `source/frontend/carla_mcp/rig/graph.py` (Tasks 1–5, already committed) against
   the brief's assumptions:
   - `Effect(handle, role, plugin, plugin_id=None, bypassed=False)` — matches brief exactly.
   - `Node` already carries all v3 fields the brief uses (`looper_id`, `port_index`,
     `main_muted`, `all_muted`, `port_pattern`, `chain_file`, `effects`).
   - `RuntimeUnit(name, kind, node=None)` — matches.
   - `RigGraph.add_edge(src, dst, gain_db=0.0, kind="audio", src_port=None, dst_port=None)` — matches.
   No discrepancies found — **zero adaptations were needed**; the brief's code was transcribed verbatim.
3. Wrote the failing test file `source/frontend/carla_mcp/tests/test_rig_session_v3.py`
   exactly as given in the brief.
4. Ran it and confirmed the expected failure:
   `ModuleNotFoundError: No module named 'carla_mcp.rig.session'`.
5. Implemented `source/frontend/carla_mcp/rig/session.py` verbatim from the brief:
   - `SESSION_FILE`, `LEGACY_MANIFEST`, `LEGACY_STATE`, `LOOPER_PROJECT` constants.
   - `SessionError` exception.
   - `RigSession` dataclass (`name`, `graph`, `carla_project`, `looper_session_dir`,
     `version_read=3`, `notes`).
   - `session_to_dict` / `session_from_dict` (strict: unknown version or unknown node/edge
     kind raises `SessionError`).
   - `write_session` (always writes v3, session-dir-relative paths, ISO `saved_at`).
   - `read_session` (v3 preferred; falls back to legacy-manifest detection, which currently
     dispatches to `_migrate_legacy`).
   - `verify_session_files` (names every missing `carla_project`, per-node `chain_file`,
     and `looper_session_dir/project.loopers`).
   - `_migrate_legacy` left as a **raising stub** (`SessionError: legacy manifest at
     {session_dir} — migrator not yet implemented`), per the brief's explicit instruction
     that it stays a stub until Task 7.
   - Confirmed stdlib-only: imports are `json`, `dataclasses`, `datetime`, `pathlib`,
     `typing`, plus intra-repo `carla_mcp.rig.graph`. No third-party imports, satisfying
     the `rig/` stdlib-only global constraint.
6. Ran the new test file: **9/9 passed**.
7. Ran the full test suite (`uv run python -m pytest source/frontend/carla_mcp/tests/ -v`):
   **590/590 passed**, no regressions.
8. Staged only the two intended files (pre-existing unrelated working-tree changes —
   `.gitignore`, `.gitmodules`, `.mcp.json`, `.env.example`, `.superpowers/` — were left
   untouched, not part of this task).
9. Committed with the brief's exact message.

## Commit

- `60c52f179` — `feat(rig): manifest v3 RigSession read/write with strict validation`
  - `source/frontend/carla_mcp/rig/session.py` (new)
  - `source/frontend/carla_mcp/tests/test_rig_session_v3.py` (new)

## Test summary

- New file: `test_rig_session_v3.py` — 9 passed.
- Full suite: **590 passed**, 0 failed, 10.45s.

## Adaptations from brief

None. The brief's JSON schema, dataclass field names, and code listing matched the
already-committed `rig/graph.py` from Tasks 1–5 exactly, so the implementation and test
file were transcribed as-is.

## Concerns / notes for Task 7

- `read_session`'s legacy branch currently only checks for `LEGACY_MANIFEST`
  (`rig_manifest.json`) to decide whether to call `_migrate_legacy`; it does not
  independently check for `LEGACY_STATE` (`rig_state.json`). This matches the brief's
  code exactly, but Task 7 (which implements the real migrator) should confirm this
  detection is sufficient or extend it if a legacy session can exist with only
  `rig_state.json` and no `rig_manifest.json`.
- `_migrate_legacy` is an intentional raising stub — any code path that reaches it today
  (e.g. `read_session` on a directory containing only `rig_manifest.json`) will raise
  `SessionError` until Task 7 lands. This is per spec, not a defect.
- No other blockers. Nothing was BLOCKED.
