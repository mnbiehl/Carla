import pytest
from looper_mcp.tools import (
    _command_for_transport,
    _command_for_looper,
)


def test_transport_start_command():
    assert _command_for_transport("start") == "Start"


def test_transport_set_tempo_command():
    assert _command_for_transport("set_tempo", bpm=120.0) == {"SetTempoBPM": 120.0}


def test_transport_set_time_signature():
    assert _command_for_transport("set_time_signature", upper=4, lower=4) == {
        "SetTimeSignature": [4, 4]
    }


def test_looper_record_command():
    assert _command_for_looper("record", target="Selected") == {
        "Looper": ["Record", "Selected"]
    }


def test_looper_record_with_index():
    assert _command_for_looper("record", target="0") == {
        "Looper": ["Record", {"Index": 0}]
    }


def test_looper_record_all():
    assert _command_for_looper("record", target="All") == {
        "Looper": ["Record", "All"]
    }


def test_looper_set_level():
    assert _command_for_looper("set_level", target="Selected", value=0.5) == {
        "Looper": [{"SetLevel": 0.5}, "Selected"]
    }


def test_looper_set_pan():
    assert _command_for_looper("set_pan", target="1", value=-0.5) == {
        "Looper": [{"SetPan": -0.5}, {"Index": 1}]
    }
