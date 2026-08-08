# Task 1 Report: Graph model v3 — new node kinds, edge kinds, explicit ports, runtime units

## Status: DONE

## What was implemented

Extended `source/frontend/carla_mcp/rig/graph.py`:

- `NODE_KINDS = ("endpoint", "track", "bus", "loop", "app", "midi")` and
  `EDGE_KINDS = ("audio", "midi")` module-level constants, added right after
  the imports.
- `Node` dataclass gained: `looper_id: Optional[int] = None`,
  `port_index: Optional[int] = None`, `main_muted: bool = False`,
  `all_muted: bool = False`, `port_pattern: Optional[str] = None`,
  `chain_file: Optional[str] = None`. Docstring updated to describe the new
  kinds and fields.
- `Edge` dataclass gained: `kind: str = "audio"`, `src_port: Optional[str] =
  None`, `dst_port: Optional[str] = None`. Docstring updated.
- New `RuntimeUnit` dataclass: `name: str`, `kind: str`, `node: Optional[str]
  = None`, as specified verbatim in the brief.
- `RigGraph.__init__` now also initializes `self.runtime_units: dict[str,
  RuntimeUnit] = {}`.
- `RigGraph.add_node` now validates `node.kind in NODE_KINDS` before the
  duplicate-name check, raising `ValueError` mentioning "kind" on failure.
- `RigGraph.add_edge` signature extended to `(src, dst, gain_db=0.0,
  kind="audio", src_port=None, dst_port=None)`. Validates `kind in
  EDGE_KINDS`. Uniqueness key changed from `(src, dst)` to `(src, dst,
  src_port, dst_port)` so node-level edges stay unique per pair while
  explicit-port edges (e.g. stereo lifts) can coexist.
- New `RigGraph.add_runtime_unit(unit)` — idempotent replace by
  `unit.name` into `self.runtime_units`.

Updated `source/frontend/carla_mcp/rig/__init__.py`:

- Added `RuntimeUnit`, `NODE_KINDS`, `EDGE_KINDS` to the import from
  `carla_mcp.rig.graph` and to `__all__`, following the file's existing
  pattern (module docstring listing exported names by submodule, explicit
  `__all__` list). No other rig submodule needed changes.

Created `source/frontend/carla_mcp/tests/test_rig_graph_v3.py` verbatim as
given in the brief (15 tests across `TestNodeKinds`, `TestEdgeKinds`,
`TestExplicitPortEdges`, `TestRuntimeUnits`).

## Deviations from the brief

None. The brief's anchors (line numbers for Node/Edge/`__init__`/`add_edge`)
were approximate as expected but the surrounding code matched closely enough
that all snippets applied with only cosmetic adjustments (docstring merge
rather than literal append, to avoid a duplicated/contradictory `kind`
description line). No third-party imports were added — `rig/graph.py`
remains stdlib-only (`dataclasses`, `typing`), satisfying the global
constraint.

## Test commands + results

1. Failing test first (before implementation):
   ```
   uv run python -m pytest source/frontend/carla_mcp/tests/test_rig_graph_v3.py -v
   ```
   Result: collection error —
   `ImportError: cannot import name 'EDGE_KINDS' from 'carla_mcp.rig.graph'`
   (as expected; `NODE_KINDS`/`RuntimeUnit` also not yet defined).

2. After implementation:
   ```
   uv run python -m pytest source/frontend/carla_mcp/tests/test_rig_graph_v3.py \
     source/frontend/carla_mcp/tests/test_rig_graph.py \
     source/frontend/carla_mcp/tests/test_rig_controller.py -v
   ```
   Result: **83 passed** (15 new + 68 existing graph/controller tests), 0
   failures.

3. Full project test suite as a broader safety check:
   ```
   uv run python -m pytest source/frontend/carla_mcp/tests/ -v
   ```
   Result: **528 passed**, 0 failures.

(All runs used `uv run python -m pytest ...` per the invocation note — bare
`uv run pytest` was not used.)

## Files changed

- `source/frontend/carla_mcp/rig/graph.py` (modified)
- `source/frontend/carla_mcp/rig/__init__.py` (modified)
- `source/frontend/carla_mcp/tests/test_rig_graph_v3.py` (new)

## Self-review findings

- Checked all other `rig/*.py` modules (`describe.py`, `controller.py`,
  `probe.py`) for hardcoded exhaustive node-kind checks that an added kind
  might silently break (e.g. an `if kind in (...) else raise` fallback that
  enumerates all kinds). Found only inclusion checks against specific kinds
  (`"endpoint"`, `("track", "bus")`), never an exhaustive enumeration —
  none needed updating and none broke.
- Verified `add_edge`'s new uniqueness key doesn't change behavior for any
  existing caller: every pre-existing call site passes no `src_port`/
  `dst_port`, so the key degenerates to the old `(src, dst, None, None)`,
  identical in effect to the previous `(src, dst)` key for all pre-v3 edges.
- No new third-party imports; `rig/graph.py` stays stdlib-only per the
  global constraint.
- Confirmed the commit only staged the three intended files — other
  working-tree changes (`.gitignore`, `.gitmodules`, `.mcp.json`,
  `.env.example`, `.superpowers/`) were pre-existing in the working tree
  from environment/session setup, unrelated to this task, and were left
  untouched/unstaged.

## Commit

`44cebb064` — "feat(rig): extend graph model with loop/app/midi nodes, edge
kinds, runtime units" on branch `feat/rig-reconciler`.
