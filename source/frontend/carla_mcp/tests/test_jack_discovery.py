"""Tests for JACK port discovery."""

import pytest
from unittest.mock import Mock, patch
from carla_mcp.state.jack_discovery import JackDiscovery, PortInfo


class TestPortInfo:
    """Test PortInfo data structure."""

    def test_port_info_creation(self):
        """Can create PortInfo."""
        info = PortInfo(
            name="looper:out_1_L",
            client="looper",
            port="out_1_L",
            is_input=False,
            is_audio=True
        )

        assert info.name == "looper:out_1_L"
        assert info.client == "looper"
        assert not info.is_input
        assert info.is_audio


class TestJackDiscovery:
    """Test JACK port discovery with mocked JACK."""

    def test_list_audio_outputs(self, mock_jack_client):
        """Lists audio output ports."""
        port1 = Mock()
        port1.name = "looper:out_1_L"
        port1.is_input = False
        port1.is_audio = True

        port2 = Mock()
        port2.name = "looper:out_1_R"
        port2.is_input = False
        port2.is_audio = True

        mock_jack_client.get_ports.return_value = [port1, port2]

        discovery = JackDiscovery(mock_jack_client)
        outputs = discovery.get_audio_outputs()

        assert len(outputs) == 2
        assert outputs[0].name == "looper:out_1_L"

    def test_list_audio_inputs(self, mock_jack_client):
        """Lists audio input ports."""
        port1 = Mock()
        port1.name = "reverb:in_L"
        port1.is_input = True
        port1.is_audio = True

        port2 = Mock()
        port2.name = "reverb:in_R"
        port2.is_input = True
        port2.is_audio = True

        mock_jack_client.get_ports.return_value = [port1, port2]

        discovery = JackDiscovery(mock_jack_client)
        inputs = discovery.get_audio_inputs()

        assert len(inputs) == 2
        assert inputs[0].is_input is True

    def test_get_client_ports(self, mock_jack_client):
        """Gets all ports for a specific client."""
        port1 = Mock()
        port1.name = "looper:out_1_L"
        port1.is_input = False
        port1.is_audio = True

        port2 = Mock()
        port2.name = "looper:out_1_R"
        port2.is_input = False
        port2.is_audio = True

        port3 = Mock()
        port3.name = "reverb:in_L"
        port3.is_input = True
        port3.is_audio = True

        mock_jack_client.get_ports.return_value = [port1, port2, port3]

        discovery = JackDiscovery(mock_jack_client)
        looper_ports = discovery.get_client_ports("looper")

        assert len(looper_ports) == 2
        assert all(p.client == "looper" for p in looper_ports)
