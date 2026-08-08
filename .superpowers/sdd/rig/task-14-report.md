# Task 14 Report: Bridge integration — managed looper, a2j lifecycle, BridgeOps, new MCP tools

## Status: COMPLETE

Branch: `feat/rig-reconciler` (verified before committing).

## What was done (strict TDD)

1. Wrote failing test `tests/test_bridge_rig_tools.py` (brief's exact content + an extra
   `TestLooperStateUnwrap` class pinning the GetState-envelope unwrap — see watchpoint (c)).
   Confirmed all 15 failed with `AttributeError: ... has no attribute 'BridgeOps'` etc.
2. Implemented `mcp_stdio_bridge.py`:
   - Added imports (`time`, `carla_mcp.rig.converge` {RigOps, do_load, do_routing_reset,
     do_save, do_stop, do_verify}, `rig.graph.RigGraph`, `rig.observe.observe as rig_observe`,
     `rig.session` {SessionError, read_session}, `utils.pw_link` {connect/disconnect/list_*},
     `looper_mcp.looper_client.LooperClient`).
   - Deleted `_build_rig_manifest`.
   - Added globals `_a2j_process`, `_a2j_log_file`, `_current_graph`, `LOOPER_JSON_PORT`.
   - `_start_looper` engine spawn is now `["pw-jack", LOOPERS_PATH, "--managed"]`.
   - Added `_is_a2j_running` / `_start_a2j` / `_stop_a2j`.
   - Added `_carla_call`, `BridgeOps(RigOps)`, and rewrote `save_rig_session` /
     `load_rig_session` as thin wrappers; added `verify_rig`, `rig_routing_reset`, `stop_rig`.
   - Extended `_atexit_cleanup` with an a2j termination block.
3. `git rm`'d `test_load_rig_routing.py`, `test_rig_routing_roundtrip.py`, `test_rig_session.py`.
4. Full suite green.

## Deviations from the brief (all mechanical, recorded)

- **GetState envelope unwrap (watchpoint c).** Verified `LooperClient.get_state()` returns the
  RAW reply `{"state": {...}}` (confirmed by `looper_mcp/tests/test_looper_client.py` which
  asserts `result["state"]["tempo_bpm"]`). The brief's `BridgeOps.observe._get_state` and
  `looper_get_state` as written do NOT unwrap. I added a module-level `_unwrap_looper_state()`
  helper (peels one `"state"` envelope, passthrough otherwise) and call it in BOTH the observe
  `_get_state` closure and `BridgeOps.looper_get_state`, so `do_save`/`observe` see
  `main_muted`/`loopers` at the top level. Pinned by 3 tests in `TestLooperStateUnwrap`
  (unwrap, passthrough-when-no-envelope, None-on-ConnectionError).
- **`test_bridge_looper_lifecycle.py` needed NO edit** (watchpoint a said it "may" assert the
  old argv). Its assertions only check `"pw-jack" in first_call_args` and Popen call count = 2;
  appending `--managed` keeps both true. Left unchanged; still passes.
- **`test_rig_session.py` deletion confirmed safe.** It contained only the two
  `_build_rig_manifest` tests (`test_rig_manifest_structure`, `test_rig_manifest_defaults`) —
  matches the brief's claim. The other two deleted files only tested the removed imperative
  v2 save/load/routing path. No other test references `save_rig_session`/`load_rig_session`/
  `_build_rig_manifest` except the new negative-assertion test.
- All real shipped symbol names matched the brief's assumptions: `_is_carla_reachable`,
  `_is_looper_reachable`, `_start_carla`/`_stop_carla`, `_start_looper`/`_stop_looper`,
  `_tool_result_json`, `sse_client`/`ClientSession`, `RIG_SESSION_DIR`, `JackRouter.list_connections`
  (callable with no required args, returns List[Tuple[str,str]]), `RuntimeUnit.node`. No adaptation
  needed beyond the unwrap above.

## Tests

Full suite: **649 passed** (`uv run python -m pytest`). Target trio
(`test_bridge_rig_tools.py` 15 + `test_start_rig.py` 3 + `test_bridge_looper_lifecycle.py` 6):
24 passed.

## Concerns

- The managed-launch test (`test_engine_launched_with_managed_flag`, brief-supplied) drives the
  real `_start_looper` MCP-reachability wait loop with `_is_looper_reachable` patched False, so it
  spends ~15s in `asyncio.sleep`. Harmless but slow; it is the brief's test verbatim.

## Fix report: garbage-looper-reply contract violation (fix-before-merge finding)

**Finding.** `LooperClient._send_and_recv` (`looper_mcp/looper_client.py`) does
`json.loads(...)` on the socket reply; a half-open socket yielding empty/garbage bytes raises
`json.JSONDecodeError` (a `ValueError` subclass). `BridgeOps._looper_command`,
`BridgeOps.looper_get_state`, and the `_get_state` closure inside `BridgeOps.observe`
(`mcp_stdio_bridge.py`) each caught only `ConnectionError`, so a garbage reply would propagate an
exception out of `do_save`/`do_load`/`observe` — violating the RigOps contract that expected
failures return error strings/None, never raise.

**Fix (minimal, TDD).**
1. Added `TestGarbageLooperReply` to `tests/test_bridge_rig_tools.py` (3 tests): patched
   `LooperClient.send_command`/`get_state` to raise `json.JSONDecodeError("Expecting value", "",
   0)` and asserted `_looper_command` returns a string, `looper_get_state` returns `None`, and the
   closure captured from `observe`'s call into `rig_observe` (via a fake `rig_observe` that
   records its kwargs) returns `None` when invoked directly. Ran first — confirmed all three
   failed with the exception propagating (uncaught `JSONDecodeError`).
2. Broadened the three catches from `except ConnectionError` to
   `except (ConnectionError, ValueError)` in `mcp_stdio_bridge.py`:
   - `BridgeOps._looper_command` (returns `str(e)`)
   - `BridgeOps.looper_get_state` (returns `None`)
   - the `_get_state` closure inside `BridgeOps.observe` (returns `None`)
3. Sanctioned cosmetic fold-in: `rig/converge.py`'s
   `return f"FAILED: nothing to save ..."` had no interpolation (F541); dropped the `f` prefix.

**Tests.**
- Covering trio: `uv run python -m pytest source/frontend/carla_mcp/tests/test_bridge_rig_tools.py
  source/frontend/carla_mcp/tests/test_rig_converge_save.py -v` → **24 passed**.
- Full suite: `uv run python -m pytest -q` → **655 passed**.

**Commit.** `816b35f9d00a392e0ee294256abec583c320ad8e` —
"fix(bridge): never raise on garbage looper replies (JSONDecodeError -> error string/None)".
