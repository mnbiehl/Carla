"""Tests for JACK router."""

import pytest
from unittest.mock import patch, Mock

from carla_mcp.orchestration.jack_router import JackRouter, RouteResult


class TestJackRouterConnect:
    def test_connect_stereo_calls_pw_link_twice(self):
        router = JackRouter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = router.connect_stereo(
                "looperdooper:loop0_out_l",
                "looperdooper:loop0_out_r",
                "CarlaChain_guitar:audio-in1",
                "CarlaChain_guitar:audio-in2",
            )
            assert result.success
            assert mock_run.call_count == 2

    def test_connect_stereo_fails_if_pw_link_fails(self):
        router = JackRouter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="not found")
            result = router.connect_stereo("a:l", "a:r", "b:l", "b:r")
            assert not result.success


class TestJackRouterDisconnect:
    def test_disconnect_stereo(self):
        router = JackRouter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = router.disconnect_stereo("a:l", "a:r", "b:l", "b:r")
            assert result.success
            assert mock_run.call_count == 2


class TestJackRouterList:
    def test_list_connections_parses_pw_output(self):
        router = JackRouter()
        pw_output = (
            "looperdooper:loop0_out_l -> CarlaChain_guitar:audio-in1\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=pw_output)
            connections = router.list_connections()
            assert len(connections) == 1
            assert connections[0] == (
                "looperdooper:loop0_out_l",
                "CarlaChain_guitar:audio-in1",
            )
