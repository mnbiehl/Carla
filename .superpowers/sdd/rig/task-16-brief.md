### Task 16: Kb hygiene

**Files:**
- Modify: `kb/Carla/design-docs/daw-style-track-rig-with-multi-instance-carla.md` (the "### Rig manifest schema" section, ~line 96)
- Modify: `kb/Carla/tech-debt/by-domain/load-rig-session-does-not-restore-external-jack-routing.md` (header fields, lines 5–12)
- Modify: `kb/Carla/exec-plans/completed/main/retro.md` (follow-up checklist, lines 55–62)

**Interfaces:** none (documentation edits; kb is a git submodule at `kb/` — commit inside it, then bump the pointer in the outer repo; publish via `reins kb publish`).

**Steps:**

- [ ] In `daw-style-track-rig-with-multi-instance-carla.md`, insert directly under the `### Rig manifest schema` heading (before the JSON block):

```markdown
> **Superseded (2026-07):** this "version 2" manifest sketch was never the
> shipped format and is now superseded by **manifest v3** (`rig_session.json`,
> single file: nodes with per-track `.carxp` pointers, typed audio/midi edges,
> looper session path, runtime-unit expectations). See
> `specs/drafts/bulletproof-rig-session-round-trip-via-unified-rig-graph-rec.md`
> and `source/frontend/carla_mcp/rig/session.py`. Kept below for history.
```

- [ ] In `load-rig-session-does-not-restore-external-jack-routing.md`, correct the false resolution: change `**Status:** resolved` to `**Status:** resolved (previously falsely resolved — regressed by 8aee121, see exec-plans/completed/main/retro.md)`, change `**Remediation:** complete` to reference the reconciler, and replace the `**Resolution:**` line with:

```markdown
**Resolution:** The 2026-04-03 fix was reverted by 8aee121 and this entry was
left incorrectly marked resolved; the 2026-04-10 retro documents the
regression. Fixed for real by the unified rig-graph reconciler
(rig/reconcile.py + rig/converge.py): load_rig_session now clean-slates all
rig port space, converges every desired edge from the v3 manifest, and
verifies structurally before reporting. 2026-07.
```

- [ ] In `retro.md`, tick the follow-up items this slice covers and annotate each with how (leave line 62's session backfill unticked — it is a live-rig operator task):
  - line 55 (reopen tech-debt entry) → `- [x] ... — done: status corrected 2026-07 (reconciler slice).`
  - line 56 (routing snapshot in save) → `- [x] ... — superseded: save_rig_session emits manifest v3 with typed edges (lift of live rig-space links), not a flat routing list.`
  - line 57 (routing replay in load) → `- [x] ... — superseded: load converges v3 edges with wait-for-ports and per-connection reporting.`
  - line 58 (clean-slate step) → `- [x] ... — done: do_load clean-slates all rig port space before converge (rig/converge.py).`
  - line 59 (`rig_routing_reset` tool) → `- [x] ... — done: rig_routing_reset MCP tool on the bridge.`
  - line 60 (restore deleted tests) → `- [x] ... — done: test_rig_roundtrip_integration.py covers stale-link clearing; pure diff/plan tests added.`
  - line 61 (v1 manifest warning) → `- [x] ... — superseded: v1 sessions migrate read-time to v3; migration notes (including "no saved routing") appear in the load report.`
- [ ] Verify kb state renders sensibly: `git -C kb diff --stat` and read each changed file once.
- [ ] Commit inside kb, then bump the pointer, then publish:
```
git -C kb add Carla/design-docs/daw-style-track-rig-with-multi-instance-carla.md Carla/tech-debt/by-domain/load-rig-session-does-not-restore-external-jack-routing.md Carla/exec-plans/completed/main/retro.md
git -C kb commit -m "docs: mark manifest v2 superseded by v3, correct routing tech-debt status, close retro follow-ups

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git add kb
git commit -m "chore: bump kb — rig reconciler doc hygiene

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

