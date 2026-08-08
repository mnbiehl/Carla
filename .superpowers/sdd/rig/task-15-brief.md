### Task 15: Integration round-trip test (save → reset → load → verify == OK)

**Files:**
- Create: `source/frontend/carla_mcp/tests/test_rig_roundtrip_integration.py`

**Interfaces:**
- Consumes the full converge stack (Tasks 6–11) through one stateful `RoundTripOps(RigOps)` fake simulating PipeWire + processes + Carla export/import + looper engine. Restores the intent of the deleted `test_load_rig_routing.py` and the retro follow-up `test_load_rig_clears_stale_links_before_restore`.

**Steps:**

- [ ] Write the test (this task is test-only; it must pass immediately if Tasks 6–11 are correct — if it fails, fix the converge engine, not the test):

```python
"""End-to-end round trip through the rig reconciler with a fake world.

build small rig -> do_save -> do_routing_reset (stale-state pollution)
-> do_load -> do_verify == OK.  Also proves clean-slate beats seeded
stale links (retro follow-up: test_load_rig_clears_stale_links_before_restore).
"""

import asyncio
import json
from pathlib import Path

from carla_mcp.rig.converge import (
    RigOps, do_load, do_routing_reset, do_save, do_verify,
)
from carla_mcp.rig.observe import Link, ObservedState
from carla_mcp.rig.session import read_session

MON0 = "alsa_output.usb-F-00.pro-output-0:playback_AUX0"
MON1 = "alsa_output.usb-F-00.pro-output-0:playback_AUX1"
CAPTURE = "alsa_input.usb-F-00.pro-input-0:capture_AUX0"
PACER = "a2j:Pacer [32] (capture): Pacer MIDI 1"
MIDI_IN = "loopers:loopers_midi_in"

LOOP_OUTS = ["loopers:loop0_out_l", "loopers:loop0_out_r"]
LOOP_INS = ["loopers:loop0_in_l", "loopers:loop0_in_r"]
CHAIN_OUTS = ["CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2"]
CHAIN_INS = ["CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2"]


class RoundTripOps(RigOps):
    """Stateful fake world: ports/links/units mutate exactly like production."""

    def __init__(self):
        self.units_up = {"carla:main", "carla:strat", "looper:engine",
                         "looper:mcp", "a2j"}
        self.outputs = set(LOOP_OUTS + CHAIN_OUTS + [CAPTURE, PACER])
        self.inputs = set(LOOP_INS + CHAIN_INS + [MIDI_IN, MON0, MON1])
        self.links = {
            (LOOP_OUTS[0], CHAIN_INS[0]), (LOOP_OUTS[1], CHAIN_INS[1]),
            (CHAIN_OUTS[0], MON0), (CHAIN_OUTS[1], MON1),
            (CAPTURE, LOOP_INS[0]), (CAPTURE, LOOP_INS[1]),
            (PACER, MIDI_IN),
        }
        self.looper_state = {"main_muted": False, "all_muted": False,
                             "loopers": [{"id": 7, "port_index": 0,
                                          "mode": "Playing", "level_db": 0.0,
                                          "pan": 0.0, "input_source": None}]}

    async def observe(self, graph):
        units = list(graph.runtime_units.values()) if graph else []
        return ObservedState(
            links=[Link(s, d) for s, d in sorted(self.links)],
            output_ports=sorted(self.outputs),
            input_ports=sorted(self.inputs),
            unit_status={u.name: u.name in self.units_up for u in units},
            looper_state=self.looper_state,
        )

    async def start_unit(self, unit):
        self.units_up.add(unit.name)
        if unit.kind == "looper-engine":
            self.outputs |= set(LOOP_OUTS)
            self.inputs |= set(LOOP_INS) | {MIDI_IN}
        return None

    async def stop_unit(self, unit):
        self.units_up.discard(unit.name)
        return None

    def connect(self, src, dst):
        if src not in self.outputs or dst not in self.inputs:
            return f"port missing: {src} -> {dst}"
        self.links.add((src, dst))
        return None

    def disconnect(self, src, dst):
        self.links.discard((src, dst))
        return None

    def wait_ports(self, ports, timeout_s=15.0):
        return [p for p in ports if p not in self.outputs | self.inputs]

    async def export_rig_state(self, chains_dir):
        Path(chains_dir).mkdir(parents=True, exist_ok=True)
        chain = Path(chains_dir) / "strat.carxp"
        chain.write_text("<carla/>")
        return {"version": 1,
                "nodes": [
                    {"name": "loopers:loop0_out", "kind": "endpoint",
                     "instance": None, "jack_client": "loopers:loop0_out",
                     "source": None, "effects": []},
                    {"name": "strat", "kind": "track", "instance": "strat",
                     "jack_client": "CarlaChain_strat",
                     "source": "loopers:loop0_out", "effects": [],
                     "chain_file": str(chain)},
                ],
                "edges": [{"src": "loopers:loop0_out", "dst": "strat",
                           "gain_db": 0.0}],
                "errors": []}

    async def save_carla_project(self, path):
        Path(path).write_text("<carla/>")
        return None

    async def load_carla_project(self, path):
        return None if Path(path).exists() else f"missing {path}"

    async def import_rig_state(self, state, chains_dir):
        for n in state["nodes"]:
            if n["kind"] in ("track", "bus"):
                c = n["jack_client"]
                self.outputs |= {f"{c}:audio-out1", f"{c}:audio-out2"}
                self.inputs |= {f"{c}:audio-in1", f"{c}:audio-in2"}
                self.units_up.add(f"carla:{n['name']}")
        return {"success": True, "tracks": [], "messages": []}

    async def looper_save_session_at(self, dir_path):
        d = Path(dir_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.loopers").write_text(json.dumps({"loopers": []}))
        return None

    async def load_looper_session(self, project_path):
        return None if Path(project_path).exists() else f"missing {project_path}"

    async def looper_get_state(self):
        return self.looper_state

    async def set_looper_mutes(self, main_muted, all_muted):
        self.looper_state["main_muted"] = main_muted
        self.looper_state["all_muted"] = all_muted
        return None


class TestRoundTrip:
    def test_save_reset_load_verify_is_ok(self, tmp_path):
        ops = RoundTripOps()
        sdir = tmp_path / "roundtrip"

        save_report = asyncio.run(do_save("roundtrip", sdir, ops))
        assert save_report.splitlines()[0] == "OK", save_report

        # Simulate stale-state pollution: wipe rig routing, seed a garbage
        # link of the exact class from the 2026-04-10 regression retro.
        reset_report = asyncio.run(do_routing_reset(ops))
        assert reset_report.splitlines()[0] == "OK"
        assert not any("loopers" in s or "Carla" in s for s, _ in ops.links)
        ops.links.add(("loopers:loop0_out_r", "CarlaChain_strat:audio-in1"))

        load_report = asyncio.run(do_load("roundtrip", sdir, ops))
        assert load_report.splitlines()[0] == "OK", load_report

        # Stale crossed link is gone; desired wiring is back, L->L R->R.
        assert ("loopers:loop0_out_r", "CarlaChain_strat:audio-in1") not in ops.links
        assert (LOOP_OUTS[0], CHAIN_INS[0]) in ops.links
        assert (LOOP_OUTS[1], CHAIN_INS[1]) in ops.links
        assert (CAPTURE, LOOP_INS[0]) in ops.links
        assert (PACER, MIDI_IN) in ops.links

        graph = read_session(sdir).graph
        verify_report = asyncio.run(do_verify(graph, ops))
        assert verify_report.splitlines()[0] == "OK", verify_report

    def test_round_trip_survives_full_process_restart(self, tmp_path):
        ops = RoundTripOps()
        sdir = tmp_path / "restart"
        asyncio.run(do_save("restart", sdir, ops))

        # Cold world: every process down, all rig ports and links gone.
        ops.units_up.clear()
        ops.links.clear()
        ops.outputs = {CAPTURE, PACER}
        ops.inputs = {MON0, MON1}

        load_report = asyncio.run(do_load("restart", sdir, ops))
        assert load_report.splitlines()[0] == "OK", load_report
        graph = read_session(sdir).graph
        assert asyncio.run(do_verify(graph, ops)).splitlines()[0] == "OK"
```

- [ ] Run: `uv run pytest source/frontend/carla_mcp/tests/test_rig_roundtrip_integration.py -v` — must pass; any failure is a converge-engine bug to fix (use systematic debugging, keep this test as the spec).
- [ ] Run the whole suite once more: `uv run pytest`
- [ ] Commit:
```
git add source/frontend/carla_mcp/tests/test_rig_roundtrip_integration.py
git commit -m "test(rig): round-trip integration — save, reset, pollute, load, verify OK

Restores the intent of the deleted test_load_rig_routing.py and the retro's
test_load_rig_clears_stale_links_before_restore follow-up.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

