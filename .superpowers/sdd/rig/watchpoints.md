## Risks / watchpoints

- `test_bridge_looper_lifecycle.py` may assert the old engine argv — update it in Task 14 for `--managed`.
- `session._lift_rig_state` is shared by migration and live save (`_graph_from_export`) on purpose; changing one changes both — that is the point, keep it that way.
- `pw-link -l` parsing already exists in two dialects (`JackRouter.list_connections` vs `pw_link_verify`); the reconciler standardizes on `JackRouter.list_connections`. Do not add a third parser.
- The Rust remote's `GetState` reply nests everything under a `"state"` key (`{"state": {..., "loopers": [...]}}`). `do_save`/`observe` read `main_muted`/`loopers` at the TOP level of what `looper_get_state()` returns — so `LooperClient.get_state()` (or `BridgeOps.looper_get_state`) must unwrap the envelope and return the inner `state` object. Verify against `looper_mcp/looper_client.py` in Task 14 and add an unwrap there if it returns the raw reply.
- The rig graph inside the main Carla process is separate from the session graph the bridge holds; `rig_state_for_import` passes `edges=[]` so `RigController.route` (create_track's source wiring aside) never fights the converge engine over links.

