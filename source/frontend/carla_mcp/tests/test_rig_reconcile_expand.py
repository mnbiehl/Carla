"""Tests for rig/reconcile.py port expansion — the pure desired-state surface."""

from carla_mcp.rig.graph import Node, RigGraph
from carla_mcp.rig.reconcile import (
    LOOPER_MIDI_IN, PortPair, canonical_ports, expand_edges,
    in_rig_port_space, make_port_pairs, node_input_ports, node_output_ports,
    resolve_stereo_ports,
)

MONITORS = [
    "alsa_output.usb-Focusrite-00.pro-output-0:playback_AUX0",
    "alsa_output.usb-Focusrite-00.pro-output-0:playback_AUX1",
]
CAPTURE = "alsa_input.usb-Focusrite-00.pro-input-0:capture_AUX0"


def _rig():
    """loop:0 -> strat (track) -> out:main, capture -> loop:0, pacer midi -> looper."""
    g = RigGraph()
    g.add_node(Node(name="loop:0", kind="loop", looper_id=7, port_index=0))
    g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat"))
    g.add_node(Node(name="out:main", kind="endpoint"))
    g.add_node(Node(name="in:guitar", kind="endpoint", jack_client=CAPTURE))
    g.add_node(Node(name="app:looper", kind="app"))
    g.add_node(Node(name="midi:pacer", kind="midi", port_pattern=r"a2j:.*Pacer.*capture"))
    g.add_edge("loop:0", "strat")
    g.add_edge("strat", "out:main")
    g.add_edge("in:guitar", "loop:0")
    g.add_edge("midi:pacer", "app:looper", kind="midi")
    return g


LIVE_OUTPUTS = [
    "loopers:loop0_out_l", "loopers:loop0_out_r",
    "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2",
    CAPTURE,
    "a2j:Pacer [32] (capture): Pacer MIDI 1",
]
LIVE_INPUTS = [
    "loopers:loop0_in_l", "loopers:loop0_in_r",
    "CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
    LOOPER_MIDI_IN,
] + MONITORS


class TestPortRules:
    def test_resolve_l_r_suffix(self):
        avail = ["x_l", "x_r", "y"]
        assert resolve_stereo_ports("x", avail) == ["x_l", "x_r"]

    def test_resolve_numeric_suffix(self):
        assert resolve_stereo_ports("x", ["x1", "x2"]) == ["x1", "x2"]

    def test_resolve_mono(self):
        assert resolve_stereo_ports("y", ["y"]) == ["y"]

    def test_resolve_none(self):
        assert resolve_stereo_ports("z", ["a"]) == []

    def test_pairs_stereo_straight(self):
        assert make_port_pairs(["l", "r"], ["L", "R"]) == [("l", "L"), ("r", "R")]

    def test_pairs_mono_fanout(self):
        assert make_port_pairs(["m"], ["L", "R"]) == [("m", "L"), ("m", "R")]

    def test_pairs_stereo_sum(self):
        assert make_port_pairs(["l", "r"], ["M"]) == [("l", "M"), ("r", "M")]


class TestNodePorts:
    def test_loop_output_ports(self):
        n = Node(name="loop:0", kind="loop", port_index=0)
        assert node_output_ports(n, LIVE_OUTPUTS) == ["loopers:loop0_out_l", "loopers:loop0_out_r"]

    def test_loop_input_ports(self):
        n = Node(name="loop:0", kind="loop", port_index=0)
        assert node_input_ports(n, LIVE_INPUTS) == ["loopers:loop0_in_l", "loopers:loop0_in_r"]

    def test_track_ports_filtered_to_live(self):
        n = Node(name="strat", kind="track", jack_client="CarlaChain_strat")
        assert node_output_ports(n, []) == []
        assert node_output_ports(n, LIVE_OUTPUTS) == [
            "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2"]

    def test_app_input_is_midi_in(self):
        n = Node(name="app:looper", kind="app")
        assert node_input_ports(n, LIVE_INPUTS) == [LOOPER_MIDI_IN]

    def test_midi_node_matches_pattern(self):
        n = Node(name="midi:pacer", kind="midi", port_pattern=r"a2j:.*Pacer.*capture")
        assert node_output_ports(n, LIVE_OUTPUTS) == ["a2j:Pacer [32] (capture): Pacer MIDI 1"]

    def test_out_main_resolves_monitor_regex(self):
        n = Node(name="out:main", kind="endpoint")
        assert node_input_ports(n, LIVE_INPUTS) == MONITORS

    def test_canonical_ports_track(self):
        n = Node(name="strat", kind="track", jack_client="CarlaChain_strat")
        assert canonical_ports(n) == [
            "CarlaChain_strat:audio-in1", "CarlaChain_strat:audio-in2",
            "CarlaChain_strat:audio-out1", "CarlaChain_strat:audio-out2"]

    def test_canonical_ports_loop(self):
        n = Node(name="loop:2", kind="loop", port_index=2)
        assert canonical_ports(n) == [
            "loopers:loop2_in_l", "loopers:loop2_in_r",
            "loopers:loop2_out_l", "loopers:loop2_out_r"]


class TestExpandEdges:
    def test_full_rig_expands_to_expected_pairs(self):
        exp = expand_edges(_rig(), LIVE_OUTPUTS, LIVE_INPUTS)
        pairs = {(p.src, p.dst) for p in exp.pairs}
        assert ("loopers:loop0_out_l", "CarlaChain_strat:audio-in1") in pairs
        assert ("loopers:loop0_out_r", "CarlaChain_strat:audio-in2") in pairs
        assert ("CarlaChain_strat:audio-out1", MONITORS[0]) in pairs
        assert ("CarlaChain_strat:audio-out2", MONITORS[1]) in pairs
        # mono capture fans out to both loop inputs
        assert (CAPTURE, "loopers:loop0_in_l") in pairs
        assert (CAPTURE, "loopers:loop0_in_r") in pairs
        assert ("a2j:Pacer [32] (capture): Pacer MIDI 1", LOOPER_MIDI_IN) in pairs
        assert exp.dead_ports == [] and exp.absent_nodes == []

    def test_midi_pair_carries_midi_kind(self):
        exp = expand_edges(_rig(), LIVE_OUTPUTS, LIVE_INPUTS)
        midi = [p for p in exp.pairs if p.kind == "midi"]
        assert midi == [PortPair("a2j:Pacer [32] (capture): Pacer MIDI 1", LOOPER_MIDI_IN, "midi")]

    def test_dead_track_reports_absent_and_dead_ports(self):
        outs = [p for p in LIVE_OUTPUTS if "CarlaChain" not in p]
        ins = [p for p in LIVE_INPUTS if "CarlaChain" not in p]
        exp = expand_edges(_rig(), outs, ins)
        assert "strat" in exp.absent_nodes
        assert any("strat" in m for m in exp.dead_ports)
        assert "CarlaChain_strat:audio-in1" in exp.waitable_ports

    def test_explicit_port_edge_bypasses_expansion(self):
        g = RigGraph()
        g.add_node(Node(name="cap", kind="endpoint", jack_client=CAPTURE))
        g.add_node(Node(name="loop:0", kind="loop", port_index=0))
        g.add_edge("cap", "loop:0", src_port=CAPTURE, dst_port="loopers:loop0_in_r")
        exp = expand_edges(g, [CAPTURE], ["loopers:loop0_in_l", "loopers:loop0_in_r"])
        assert exp.pairs == [PortPair(CAPTURE, "loopers:loop0_in_r", "audio")]

    def test_explicit_port_edge_dead_when_port_missing(self):
        g = RigGraph()
        g.add_node(Node(name="cap", kind="endpoint", jack_client=CAPTURE))
        g.add_node(Node(name="loop:0", kind="loop", port_index=0))
        g.add_edge("cap", "loop:0", src_port=CAPTURE, dst_port="loopers:loop0_in_r")
        exp = expand_edges(g, [CAPTURE], [])
        assert exp.pairs == []
        assert any("loopers:loop0_in_r" in m for m in exp.dead_ports)
        assert "loopers:loop0_in_r" in exp.waitable_ports


class TestRigPortSpace:
    def test_loopers_to_carla_in_space(self):
        assert in_rig_port_space("loopers:loop0_out_l", "Carla:audio-in3")

    def test_chain_to_hardware_in_space(self):
        assert in_rig_port_space("CarlaChain_strat:audio-out1", MONITORS[0])

    def test_hardware_to_loopers_in_space(self):
        assert in_rig_port_space(CAPTURE, "loopers:loop0_in_l")

    def test_midi_into_looper_in_space(self):
        assert in_rig_port_space("a2j:Pacer [32] (capture): Pacer MIDI 1", LOOPER_MIDI_IN)

    def test_unrelated_apps_untouched(self):
        assert not in_rig_port_space("Firefox:output_FL", MONITORS[0])
