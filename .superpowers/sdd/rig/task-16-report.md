# Task 16 Report: Kb hygiene

## Status: DONE

## Commits
- kb (submodule, `main`): `f04c150` — docs: mark manifest v2 superseded by v3, correct routing tech-debt status, close retro follow-ups
- outer (`feat/rig-reconciler`): `8fc14f35a` — chore: bump kb — rig reconciler doc hygiene

## What was done
- Read `task-16-brief.md` in full before touching anything.
- Verified branch: outer repo on `feat/rig-reconciler`; kb submodule HEAD was
  `3f9d157` (already committed, clean) before edits.
- Located all three anchors by heading/text (not by line number) and confirmed
  each matched the brief's description before editing:
  1. `kb/Carla/design-docs/daw-style-track-rig-with-multi-instance-carla.md` —
     `### Rig manifest schema` heading at line 96, immediately followed by the
     "Replaces the current single-instance rig manifest" JSON block.
  2. `kb/Carla/tech-debt/by-domain/load-rig-session-does-not-restore-external-jack-routing.md`
     — header fields (`Status`/`Remediation`/`Resolution`) at lines 5, 11, 12,
     matching the brief's lines 5–12 exactly.
  3. `kb/Carla/exec-plans/completed/main/retro.md` — `## Follow-ups` checklist
     at lines 55–62, item text matching the brief's paraphrases closely enough
     to map 1:1 by meaning (no reordering or renumbering needed).
- Made the three edits:
  1. Inserted the supersede blockquote verbatim under the `### Rig manifest
     schema` heading, before the JSON block. Verified the two referenced
     paths it cites exist: `kb/Carla/specs/drafts/bulletproof-rig-session-round-trip-via-unified-rig-graph-rec.md`
     and `source/frontend/carla_mcp/rig/session.py`.
  2. Changed `**Status:** resolved` → `**Status:** resolved (previously
     falsely resolved — regressed by 8aee121, see
     exec-plans/completed/main/retro.md)`; `**Remediation:** complete` →
     `**Remediation:** complete via unified rig-graph reconciler` (brief said
     "reference the reconciler," left exact wording to judgment); replaced
     the `**Resolution:**` line with the brief's verbatim replacement text.
  3. Ticked 7 of the 8 checklist items (lines 55–61) with the brief's exact
     `[x] ... — <how>` annotations appended, matched item-by-item by meaning.
     Left line 62 (`Backfill the broken saved session` — live-rig operator
     task) unticked, as explicitly instructed.
- Verified rendering: `git -C kb diff --stat` showed exactly the 3 intended
  files changed (plus an unrelated `.obsidian/workspace.json` 2-line diff —
  Obsidian's own "last opened files" cache noise from editing, not staged or
  committed). Read each of the 3 changed files once after editing to confirm
  the edits rendered as intended (blockquote placement, header fields, all
  8 checklist lines including the still-open one).
- Ran `uv run python -m pytest -q` before the outer commit: **652 passed**,
  0 failed, ~27s — tree green (docs-only change, no regressions expected or
  found).
- Committed inside kb with the brief's exact `git -C kb add` file list and
  exact commit message.
- Staged only `kb` in the outer repo (`git add kb`) and committed with the
  brief's exact message. Confirmed via `git status --short` / `git show
  --stat` that the outer commit touched only the `kb` submodule pointer —
  the pre-existing unrelated outer-repo changes (`.gitignore`, `.gitmodules`,
  `.mcp.json`, untracked `.env.example`, `.superpowers/`) were left exactly
  as they were before this task, both before and after.
- Did not run any `reins` command. Did not push (kb or outer).

## Deviations from the brief
- **Remediation field wording**: brief said "change `**Remediation:**
  complete` to reference the reconciler" without giving exact replacement
  text (unlike the `Status` and `Resolution` fields, which had exact text).
  Used `complete via unified rig-graph reconciler` — judgment call, not
  verbatim brief text since none was given.
- No other deviations. Supersede note, Status/Resolution text, and all 7
  checklist annotations are verbatim from the brief.

## Anchor-matching note
The brief's line numbers (~96, 5–12, 55–62) all matched the real files
almost exactly — no drift found. All 7 follow-up checklist items the brief
expected were present and matched 1:1 by meaning to the brief's paraphrased
descriptions; none were absent or needed to be invented.

## Concerns
- The `.obsidian/workspace.json` diff (2 added lines, editor "recently
  opened" cache referencing the `.tmp` files created during editing) is
  present in the kb working tree but was deliberately left unstaged/
  uncommitted, per the brief's explicit file list for the kb commit. It will
  remain as an uncommitted local diff in the kb submodule after this task;
  harmless, but flagging in case a later `reins kb publish` step (not run
  here) expects a clean kb tree.
- No other concerns. Docs-only change; full test suite green; commits match
  the brief's exact messages and file lists.
