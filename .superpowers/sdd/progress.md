# SDD Ledger — feat/rig-reconciler

Plan: kb/Carla/exec-plans/active/feat-rig-reconciler/plan.md (16 tasks). Spec: kb/Carla/specs/drafts/bulletproof-rig-session-round-trip-*.md
Baseline: 533 tests green at 5f2952932 (empty divergence commit over main 9ff9921-lineage).
INVOCATION NOTE: run tests as `uv run python -m pytest` — bare `uv run pytest` breaks: source/mcp shadows the mcp package under the console-script entrypoint.
Companion Rust plan: COMPLETE, looperdooper feat/rig-managed-mode @ 1466448 pushed, MERGE-READY (unmerged; contract live-verified).
Model policy: sonnet implementer+reviewer for transcription tasks; opus for Tasks 9, 10, 14 (converge load/save, bridge integration) + final review fable.
Briefs: .superpowers/sdd/rig/task-N-brief.md + global-constraints.md + watchpoints.md

## Progress
- Task 1 BASE: 5f2952932
- Task 1: complete (commit 44cebb064, review clean — graph v3 model exact. MINOR for final review: remove_edge still keys on (src,dst) only, silently removes first of multiple port-level edges. Report miscounted suite 528 vs real 547 — verified green)
- Task 2 BASE: 44cebb064
- Task 2: complete (commit b024fbf28, review clean — ObservedState model, loop discovery, 556 green)
- Task 3 BASE: b024fbf28
- Task 3: complete (commit f7bd6a760, review clean — port expansion byte-identical to controller rules; 562 green. MINORS: unused imports Optional/Link/ObservedState (brief-verbatim, staged for Task 4); out:main capped [:2])
- Task 4 BASE: f7bd6a760
- Task 4: complete (commit 29b4a677a, review clean incl adversarial probes — diff engine pure, no double-counting, reversed-link semantics correct; 573 green)
- Task 5 BASE: 29b4a677a
- Task 5: complete (commit d557791be, review clean — Action/plan/render_report verbatim, no-mutation verified; 581 green)
- Task 6 BASE: d557791be
- Task 6: complete (commit 60c52f179, review clean — manifest v3 exact, 590 green. MINOR for final review: session_from_dict raises bare KeyError not SessionError on missing required keys (brief-verbatim); Task 7 to confirm legacy detection via rig_manifest.json presence is sufficient)
- Task 7 BASE: 60c52f179
- Task 7: complete (commit 9772c32ed, review clean — migrator lifts all 5 real sessions read-only (8/6, 2/0, 0/0, 10/13, 7/5 nodes/edges), ordering-dependency + colon-name checks passed. USER AWARENESS: quartet-autoeq-wip + quartet-build reference looper session dirs missing on disk (pre-existing, named in notes))
- Task 8 BASE: 9772c32ed
- Task 8: complete (commit cb0771ae9, review clean — RigOps 14 methods, reset/verify, staged imports accounted exactly to Tasks 9-10; 603 green)
- Task 9 BASE: cb0771ae9
- Task 9: complete (commit 03439fa16, opus adversarial review clean — do_load sequence exact, retry pass disconnects unexpected links (neutralizes retro's scramble bug), idempotent re-load. MINORS: import_rig_state success flag ignored (messages only); no pre-flight verify_session_files; unused name param (brief-mandated). LIVE RISK flagged: single-retry vs PipeWire re-restoration timing untested at integration level)
- Task 10 BASE: 03439fa16
- Task 10: complete (commits 82df51609+80e3b23ca — do_save + self-verify + link lifting; opus review found IMPORTANT silent-drop of port_index-less loopers (brief bug vs global constraint), fixed with named notes + mixed-case regression test, re-review APPROVED. MINOR: F541 no-interp f-string. Round-trip seam loop:N<->loopers:loopN_out verified. Full suite now 633 (both test dirs))
- Task 11 BASE: 80e3b23ca
- Task 11: complete (commit 5617aaea7, review clean — do_stop reverse teardown; PLAN BUG caught+fixed: brief's negated-start-rank sort key put a2j 3rd, contradicting brief's own prose+test; local UNIT_STOP_ORDER dict used instead, adjudicated correct)
- Task 12 BASE: 5617aaea7
- Task 12: complete (commit 191696afd, review clean — observe() shielded probes, snapshot_handles pure append to shipped controller, rig_handles registered without reorder, all 4 count literals bumped incl 2 the brief missed)
- Task 13 BASE: 191696afd
- Task 13: complete (commit 59a8e23a5, review clean — 3 looper MCP tools, wire keys verified byte-for-byte against Rust api.rs on companion branch)
- Task 14 BASE: 59a8e23a5
- Task 14: complete (commit c5f26038e, opus adversarial review clean — BridgeOps full RigOps, GetState envelope unwrap caught+pinned (brief would have shipped broken), _stop_looper double-call safe, no stale-graph path. MINORS for final review: (1) start_unit "exited" heuristic drops non-exited failure diagnostics from Notes (spec-inherited; verdict still degrades downstream); (2) do_save's direct looper_get_state can propagate JSONDecodeError on half-open socket — violates never-raise contract, 3-line catch would fix. SSE cross-process arg shapes unverified end-to-end)
- Task 15 BASE: c5f26038e
- Task 15: complete (commits e1179c44b + 3f9f97fb2 — round-trip integration passed first try; review found tests couldn't distinguish clean-slate from retry-disconnect; added ordering-pin test with negative control (FAILS without clean-slate block: disconnect@7 vs first connect@0). 652 green)
- Task 16 BASE: 3f9f97fb2
- Task 16: complete (kb f04c150 + outer 8fc14f35a — 3 doc edits, backfill item left unticked. Obsidian workspace noise reverted in kb)
- ALL 16 TASKS DONE. Final whole-branch review (fable) next. MERGE_BASE: 5f2952932
- FINAL REVIEW (fable): MERGE-READY, one fix-before-merge (JSONDecodeError leak) fixed in 816b35f9d + re-review pending; IMPORTANT follow-up recommended post-merge: diff() should compare live mute state vs app:looper (verify_rig currently blind to mute drift). Minor triage: all leave. Live-integration risk register in final review (top: merge Rust branch FIRST — bridge hard-requires --managed binary).
- Branch pushed. 655 tests green.
- Fix re-review APPROVED. FINAL VERDICT: MERGE-READY unconditional (this repo). Sequencing: Rust branch must merge+build FIRST (bridge unconditionally passes --managed). PYTHON PLAN COMPLETE at 816b35f9d, awaiting user merge decision.
