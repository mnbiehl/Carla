"""Tests for rig/observe.py data model — Link, ObservedState, loop discovery."""

from carla_mcp.rig.observe import (
    Link, ObservedState, is_midi_port, loop_nodes_from_looper_state,
)


class TestLink:
    def test_link_is_hashable(self):
        assert {Link("a:1", "b:1"), Link("a:1", "b:1")} == {Link("a:1", "b:1")}


class TestIsMidiPort:
    def test_a2j_port_is_midi(self):
        assert is_midi_port("a2j:PACER MIDI [40] (capture): PACER MIDI MIDI 1")

    def test_loopers_midi_in_is_midi(self):
        assert is_midi_port("loopers:loopers_midi_in")

    def test_audio_port_is_not_midi(self):
        assert not is_midi_port("loopers:loop0_out_l")
        assert not is_midi_port("Carla:audio-in1")


class TestLoopDiscovery:
    def test_loops_discovered_from_getstate(self):
        state = {
            "loopers": [
                {"id": 7, "port_index": 0, "mode": "Playing", "level_db": 0.0,
                 "pan": 0.0, "input_source": None},
                {"id": 3, "port_index": 1, "mode": "Recording", "level_db": -6.0,
                 "pan": 1.0, "input_source": None},
            ]
        }
        nodes = loop_nodes_from_looper_state(state)
        assert [n.name for n in nodes] == ["loop:0", "loop:1"]
        assert nodes[0].kind == "loop"
        assert nodes[0].looper_id == 7
        assert nodes[1].port_index == 1

    def test_none_state_yields_no_loops(self):
        assert loop_nodes_from_looper_state(None) == []

    def test_legacy_getstate_without_loopers_key(self):
        assert loop_nodes_from_looper_state({"tempo": 120}) == []

    def test_looper_entry_without_port_index_skipped(self):
        state = {"loopers": [{"id": 1}]}
        assert loop_nodes_from_looper_state(state) == []


class TestObservedState:
    def test_defaults_are_empty(self):
        o = ObservedState()
        assert o.links == [] and o.unit_status == {} and o.looper_state is None
