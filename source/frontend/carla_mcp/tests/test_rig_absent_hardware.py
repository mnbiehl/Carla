"""A session keeps its audio interface and MIDI controller while they are
unplugged: the diff names the device once, a load does not wait for it, and a
save neither drops its routing nor adopts the onboard-audio fallback links."""

import asyncio

from carla_mcp.rig.converge import do_load, do_save
from carla_mcp.rig.graph import RigGraph
from carla_mcp.rig.observe import Link, ObservedState
from carla_mcp.rig.reconcile import diff, port_device
from carla_mcp.rig.session import read_session
from carla_mcp.rig.state_view import build_state
from carla_mcp.tests.test_rig_converge_load import LoadFakeOps
from carla_mcp.tests.test_rig_converge_save import CAPTURE, MIDI_IN, PACER, SaveFakeOps

ONBOARD = "alsa_output.pci-0000_00_1f.3.analog-stereo:playback_FL"
MIDI_THROUGH = "a2j:Midi Through [14] (capture): Midi Through Port-0"
SCARLETT_IN = "alsa_input.usb-F-00.pro-input-0"


def _saved_with_hardware(tmp_path) -> RigGraph:
    sdir = tmp_path / "with-hw"
    asyncio.run(do_save("with-hw", sdir, SaveFakeOps()))
    return read_session(sdir).graph


class UnpluggedOps(SaveFakeOps):
    """Same rig, Scarlett and PACER unplugged; PipeWire linked fallbacks instead."""

    def __init__(self):
        super().__init__()
        self.outputs = [p for p in self.outputs if p not in (CAPTURE, PACER)] + [MIDI_THROUGH]
        self.links = [l for l in self.links if l.src not in (CAPTURE, PACER)]
        self.links.append(Link(MIDI_THROUGH, MIDI_IN))


def _observed(ops) -> ObservedState:
    return ObservedState(links=ops.links, output_ports=ops.outputs, input_ports=ops.inputs,
                         unit_status={})


def test_port_device_names_the_a2j_device_not_the_a2j_client():
    assert port_device(PACER) == "a2j:Pacer"
    assert port_device(CAPTURE) == SCARLETT_IN


def test_diff_reports_each_missing_device_once(tmp_path):
    graph = _saved_with_hardware(tmp_path)
    graph.runtime_units.clear()
    issues = diff(graph, _observed(UnpluggedOps())).issues()
    assert issues == [
        "unexpected connection: " + MIDI_THROUGH + " -> " + MIDI_IN,
        f"device not found: {SCARLETT_IN} (2 session edges kept, not connected; "
        "ports: capture_AUX0)",
        "device not found: a2j:Pacer (1 session edges kept, not connected; "
        "ports: Pacer [32] (capture): Pacer MIDI 1)",
    ]


def test_missing_port_of_a_live_device_is_a_port_line(tmp_path):
    graph = _saved_with_hardware(tmp_path)
    graph.runtime_units.clear()
    ops = UnpluggedOps()
    ops.outputs.append(f"{SCARLETT_IN}:capture_AUX1")  # interface present, AUX0 gone
    issues = diff(graph, _observed(ops)).issues()
    assert f"port not live: {CAPTURE} (2 session edges not connected)" in issues
    assert not any(i.startswith(f"device not found: {SCARLETT_IN}") for i in issues)


def test_state_marks_the_fallback_link_as_a_stand_in(tmp_path):
    graph = _saved_with_hardware(tmp_path)
    graph.runtime_units.clear()
    state = build_state(graph, _observed(UnpluggedOps()), [], {}, "with-hw")
    assert [n for n in state["notes"] if n.startswith("stand-in: ")] == [
        f"stand-in: {MIDI_THROUGH} -> {MIDI_IN} replaces a session device that is not "
        "connected (not saved by session_save)"]


def test_save_without_the_hardware_keeps_its_routing(tmp_path):
    desired = _saved_with_hardware(tmp_path)
    sdir = tmp_path / "resave"
    report = asyncio.run(do_save("resave", sdir, UnpluggedOps(), desired=desired))
    assert report.splitlines()[0] == "OK", report
    graph = read_session(sdir).graph
    ports = {(e.src_port, e.dst_port) for e in graph.edges if e.src_port}
    assert ports == {(CAPTURE, "loopers:loop0_in_l"), (CAPTURE, "loopers:loop0_in_r"),
                     (PACER, MIDI_IN)}
    assert "a2j" in graph.runtime_units
    assert "[Warnings]" in report
    assert f"device not found: {SCARLETT_IN}; kept its 2 session edges" in report
    assert "device not found: a2j:Pacer; kept its 1 session edges" in report
    assert f"not saved: {MIDI_THROUGH} -> {MIDI_IN}" in report


KEYSTATION = "a2j:Keystation [40] (capture): Keystation MIDI 1"


def test_a_second_controller_the_session_wants_is_not_a_stand_in(tmp_path):
    with_both = SaveFakeOps()
    with_both.outputs.append(KEYSTATION)
    with_both.links.append(Link(KEYSTATION, MIDI_IN))
    asyncio.run(do_save("both", tmp_path / "both", with_both))
    desired = read_session(tmp_path / "both").graph

    ops = UnpluggedOps()  # PACER and Scarlett gone, Keystation still linked
    ops.outputs.append(KEYSTATION)
    ops.links.append(Link(KEYSTATION, MIDI_IN))
    report = asyncio.run(do_save("resave", tmp_path / "resave", ops, desired=desired))
    ports = {(e.src_port, e.dst_port) for e in read_session(tmp_path / "resave").graph.edges}
    assert (KEYSTATION, MIDI_IN) in ports and (PACER, MIDI_IN) in ports
    assert f"not saved: {KEYSTATION}" not in report


def test_a_device_replugged_under_a_new_client_number_replaces_its_stale_edge(tmp_path):
    desired = _saved_with_hardware(tmp_path)
    replugged = PACER.replace("[32]", "[36]")
    ops = SaveFakeOps()
    ops.outputs = [replugged if p == PACER else p for p in ops.outputs]
    ops.links = [Link(replugged, MIDI_IN) if l.src == PACER else l for l in ops.links]
    report = asyncio.run(do_save("resave", tmp_path / "resave", ops, desired=desired))
    midi = {e.src_port for e in read_session(tmp_path / "resave").graph.edges if e.kind == "midi"}
    assert midi == {replugged}
    assert "[Warnings]" not in report


def test_a_corrupt_session_being_overwritten_does_not_block_the_save(tmp_path):
    from carla_mcp.bridge.app import Bridge
    from carla_mcp.bridge.tools.sessions import _desired_for_save
    sdir = tmp_path / "bad"
    sdir.mkdir()
    (sdir / "rig_session.json").write_text('{"version": 3, "nodes": [{}], "edges": []}')
    assert _desired_for_save(Bridge.for_tests(), sdir) is None


def test_save_without_a_loaded_session_still_lifts_every_live_link(tmp_path):
    sdir = tmp_path / "fresh"
    asyncio.run(do_save("fresh", sdir, UnpluggedOps()))
    ports = {(e.src_port, e.dst_port) for e in read_session(sdir).graph.edges if e.src_port}
    assert ports == {(MIDI_THROUGH, MIDI_IN)}


def test_hand_unlinking_live_hardware_is_still_saved_as_a_removal(tmp_path):
    desired = _saved_with_hardware(tmp_path)
    ops = SaveFakeOps()  # hardware attached
    ops.links = [l for l in ops.links if l.src != PACER]
    sdir = tmp_path / "resave"
    asyncio.run(do_save("resave", sdir, ops, desired=desired))
    assert not any(e.src_port == PACER for e in read_session(sdir).graph.edges)


def test_kept_edge_is_dropped_when_its_loop_is_gone(tmp_path):
    desired = _saved_with_hardware(tmp_path)

    class LoopGone(UnpluggedOps):
        def __init__(self):
            super().__init__()
            self.inputs = [p for p in self.inputs if not p.startswith("loopers:loop0_in")]

    sdir = tmp_path / "resave"
    asyncio.run(do_save("resave", sdir, LoopGone(), desired=desired))
    assert not any(e.src_port == CAPTURE for e in read_session(sdir).graph.edges)


def test_load_does_not_wait_for_unplugged_hardware(tmp_path):
    import carla_mcp.tests.test_rig_converge_load as load_tests
    sdir = load_tests._write_v3_session(tmp_path)
    session = read_session(sdir)
    from carla_mcp.rig.graph import Node
    from carla_mcp.rig.session import write_session
    session.graph.add_node(Node(name=CAPTURE, kind="endpoint", jack_client=CAPTURE))
    session.graph.add_edge(CAPTURE, "loop:0", src_port=CAPTURE, dst_port="loopers:loop0_in_l")
    write_session(session, sdir)

    class Ops(LoadFakeOps):
        def wait_ports(self, ports, timeout_s=15.0):
            self.calls.append(("wait_ports", tuple(ports)))
            return super().wait_ports(ports, timeout_s)

    ops = Ops()
    report = asyncio.run(do_load("rt", sdir, ops))
    waited = [p for c in ops.calls if c[0] == "wait_ports" for p in c[1]]
    assert waited and CAPTURE not in waited
    assert report.splitlines()[0] == "DEGRADED: 1 issues", report
    assert f"device not found: {SCARLETT_IN} (1 session edges kept" in report
    assert "never appeared" not in report and "dead port reference" not in report
