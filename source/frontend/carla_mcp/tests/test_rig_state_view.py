import pytest

from carla_mcp.rig.graph import Node, RigGraph, RuntimeUnit
from carla_mcp.rig.observe import Link, ObservedState
from carla_mcp.rig.state_view import build_state

LOOPS = [
    {"id": 7, "name": "uke", "port_index": 0, "mode": "Playing", "level_db": -3.0, "pan": 0.0, "input_source": None},
    {"id": 9, "name": "vox", "port_index": 3, "mode": "Recording", "level_db": 0.0, "pan": 0.2, "input_source": "capture_AUX0"},
]


def _observed(links, units):
    return ObservedState(links=[Link(s, d) for s, d in links],
                         output_ports=["loopers:loop0_out_l", "loopers:loop3_out_l", "Carla:audio-out1"],
                         input_ports=["Carla:audio-in3", "CarlaChain_strat:audio-in1"],
                         unit_status=units)


def _graph():
    g = RigGraph()
    g.add_node(Node(name="loop:0", kind="loop", looper_id=7, port_index=0))
    g.add_node(Node(name="strat", kind="track", jack_client="CarlaChain_strat", source="loop:0"))
    g.add_edge("loop:0", "strat")
    g.add_runtime_unit(RuntimeUnit(name="carla:main", kind="carla-main"))
    g.add_runtime_unit(RuntimeUnit(name="looper:engine", kind="looper-engine"))
    return g


def test_no_session_is_ok_with_note():
    obs = _observed([("loopers:loop0_out_l", "Carla:audio-in3")], {})
    st = build_state(None, obs, LOOPS, {"bridge": "abc"}, session=None)
    assert st["verdict"] == "OK (no session loaded)"
    assert st["session"] is None and st["versions"] == {"bridge": "abc"}
    assert st["loops"][0]["node"] == "loop:0" and st["loops"][1]["level_db"] == 0.0
    assert st["links"] == [{"src": "loopers:loop0_out_l", "dst": "Carla:audio-in3", "desired": None}]
    assert st["units"] == {}


def test_with_graph_reports_verdict_units_and_desired_flags():
    obs = _observed([("loopers:loop0_out_l", "Carla:audio-in3")],
                    {"carla:main": True, "looper:engine": False})
    st = build_state(_graph(), obs, LOOPS, {}, session="tuesday")
    assert st["verdict"].startswith("DEGRADED")
    assert any("looper:engine" in i for i in st["issues"])
    assert st["units"] == {"carla:main": {"up": True}, "looper:engine": {"up": False}}
    assert st["links"][0]["desired"] is False   # stale link not in the desired graph
    assert st["session"] == "tuesday"


def test_focus_loop_filters_loops_and_links():
    obs = _observed([("loopers:loop0_out_l", "Carla:audio-in3"), ("loopers:loop3_out_l", "Carla:audio-in5")], {})
    st = build_state(None, obs, LOOPS, {}, session=None, focus="loop:3")
    assert [l["port_index"] for l in st["loops"]] == [3]
    assert [l["src"] for l in st["links"]] == ["loopers:loop3_out_l"]


def test_detail_diagram_and_io():
    obs = _observed([], {})
    assert "diagram" in build_state(_graph(), obs, [], {}, session="s", detail="diagram")
    io = build_state(None, obs, [], {}, session=None, detail="io")["io"]
    assert io == {"outputs": obs.output_ports, "inputs": obs.input_ports}
    with pytest.raises(ValueError):
        build_state(None, obs, [], {}, session=None, detail="bogus")


def test_non_rig_links_are_dropped():
    obs = _observed([("alsa_input:capture_AUX0", "alsa_output:playback_AUX0")], {})
    assert build_state(None, obs, [], {}, session=None)["links"] == []
