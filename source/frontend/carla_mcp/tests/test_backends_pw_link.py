from unittest.mock import patch, MagicMock

from carla_mcp.backends import pw_link

SAMPLE = """loopers:loop0_out_l
  |-> CarlaChain_strat:audio-in1
loopers:loop0_out_r
  |-> CarlaChain_strat:audio-in2
  |-> Carla:audio-in4
alsa_input.usb-Focusrite:capture_AUX0
"""


def test_parse_links_pairs_each_arrow_with_its_output():
    assert pw_link.parse_pw_link_links(SAMPLE) == [
        ("loopers:loop0_out_l", "CarlaChain_strat:audio-in1"),
        ("loopers:loop0_out_r", "CarlaChain_strat:audio-in2"),
        ("loopers:loop0_out_r", "Carla:audio-in4"),
    ]


def test_parse_links_empty_text():
    assert pw_link.parse_pw_link_links("") == []


def test_list_links_runs_pw_link_o_l():
    with patch("carla_mcp.backends.pw_link.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout=SAMPLE)
        links = pw_link.list_links()
    assert run.call_args.args[0] == ["pw-link", "-o", "-l"]
    assert len(links) == 3


def test_list_links_returns_empty_on_failure():
    with patch("carla_mcp.backends.pw_link.subprocess.run", side_effect=FileNotFoundError):
        assert pw_link.list_links() == []


def test_connect_maps_result_to_error_string():
    with patch("carla_mcp.backends.pw_link.pw_link_connect") as c:
        c.return_value = MagicMock(success=False, message="no such port")
        assert pw_link.connect("a:1", "b:1") == "no such port"
        c.return_value = MagicMock(success=True, message="")
        assert pw_link.connect("a:1", "b:1") is None
