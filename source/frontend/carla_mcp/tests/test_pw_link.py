"""Tests for pw-link utility module."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from carla_mcp.utils.pw_link import (
    PwLinkResult,
    pw_link_connect,
    pw_link_disconnect,
    pw_link_list_outputs,
    pw_link_list_inputs,
    pw_link_verify,
    find_monitor_output_ports,
    find_capture_input_ports,
    ensure_carla_to_monitors,
)


@patch("carla_mcp.utils.pw_link.subprocess.run")
def test_connect_calls_pw_link(mock_run):
    """Verify subprocess is called with correct args for connect."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = pw_link_connect("Carla:audio-out1", "Scarlett:playback_FL")
    mock_run.assert_called_once_with(
        ["pw-link", "Carla:audio-out1", "Scarlett:playback_FL"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.success is True


@patch("carla_mcp.utils.pw_link.subprocess.run")
def test_connect_failure_returns_error(mock_run):
    """returncode=1 should return PwLinkResult(success=False)."""
    mock_run.return_value = MagicMock(
        returncode=1, stdout="", stderr="failed to link ports"
    )
    result = pw_link_connect("Carla:audio-out1", "Scarlett:playback_FL")
    assert result.success is False
    assert "failed to link ports" in result.message


@patch("carla_mcp.utils.pw_link.subprocess.run")
def test_disconnect_calls_pw_link_d(mock_run):
    """Verify -d flag is passed for disconnect."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = pw_link_disconnect("Carla:audio-out1", "Scarlett:playback_FL")
    mock_run.assert_called_once_with(
        ["pw-link", "-d", "Carla:audio-out1", "Scarlett:playback_FL"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.success is True


@patch("carla_mcp.utils.pw_link.subprocess.run")
def test_list_outputs_parses_pw_link_output(mock_run):
    """Parse stdout lines from pw-link -o."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="Carla:audio-out1\nCarla:audio-out2\nLooper:output_FL\n",
        stderr="",
    )
    outputs = pw_link_list_outputs()
    mock_run.assert_called_once_with(
        ["pw-link", "-o"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert outputs == ["Carla:audio-out1", "Carla:audio-out2", "Looper:output_FL"]


@patch("carla_mcp.utils.pw_link.subprocess.run")
def test_list_inputs_parses_pw_link_output(mock_run):
    """Parse stdout lines from pw-link -i."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="Scarlett:playback_FL\nScarlett:playback_FR\n",
        stderr="",
    )
    inputs = pw_link_list_inputs()
    mock_run.assert_called_once_with(
        ["pw-link", "-i"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert inputs == ["Scarlett:playback_FL", "Scarlett:playback_FR"]


@patch("carla_mcp.utils.pw_link.subprocess.run")
def test_verify_connection_exists(mock_run):
    """Parse indented pw-link -l output to verify a connection."""
    # pw-link -l shows source ports flush-left, connected destinations indented
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=(
            "Carla:audio-out1\n"
            "   Scarlett:playback_FL\n"
            "Carla:audio-out2\n"
            "   Scarlett:playback_FR\n"
        ),
        stderr="",
    )
    assert pw_link_verify("Carla:audio-out1", "Scarlett:playback_FL") is True
    assert pw_link_verify("Carla:audio-out1", "Scarlett:playback_FR") is False
    assert pw_link_verify("Carla:audio-out2", "Scarlett:playback_FR") is True


@patch("carla_mcp.utils.pw_link.subprocess.run")
def test_connect_handles_timeout(mock_run):
    """subprocess.TimeoutExpired should return graceful failure."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="pw-link", timeout=5)
    result = pw_link_connect("Carla:audio-out1", "Scarlett:playback_FL")
    assert result.success is False
    assert "timeout" in result.message.lower()


@patch("carla_mcp.utils.pw_link.subprocess.run")
def test_connect_handles_missing_pw_link(mock_run):
    """FileNotFoundError should return graceful failure."""
    mock_run.side_effect = FileNotFoundError("pw-link not found")
    result = pw_link_connect("Carla:audio-out1", "Scarlett:playback_FL")
    assert result.success is False
    assert "not found" in result.message.lower() or "pw-link" in result.message.lower()


@patch("carla_mcp.utils.pw_link.pw_link_list_inputs")
def test_find_monitor_output_ports_matches_alsa_pro_output(mock_list_inputs):
    """Only alsa_output.*pro-output.*playback_AUX ports should be returned."""
    mock_list_inputs.return_value = [
        "alsa_output.usb-Focusrite_Scarlett_18i20_USB-00.pro-output-0:playback_AUX0",
        "alsa_output.usb-Focusrite_Scarlett_18i20_USB-00.pro-output-0:playback_AUX1",
        "Carla:audio-in1",
        "Firefox:output_FL",
        "alsa_output.pci-something:playback_FL",
    ]
    result = find_monitor_output_ports()
    assert result == [
        "alsa_output.usb-Focusrite_Scarlett_18i20_USB-00.pro-output-0:playback_AUX0",
        "alsa_output.usb-Focusrite_Scarlett_18i20_USB-00.pro-output-0:playback_AUX1",
    ]


@patch("carla_mcp.utils.pw_link.pw_link_list_inputs")
def test_find_monitor_output_ports_returns_empty_on_no_match(mock_list_inputs):
    """No pro-output ports should yield an empty list."""
    mock_list_inputs.return_value = [
        "Carla:audio-in1",
        "Firefox:output_FL",
        "alsa_output.pci-something:playback_FL",
    ]
    result = find_monitor_output_ports()
    assert result == []


@patch("carla_mcp.utils.pw_link.pw_link_list_outputs")
def test_find_capture_input_ports_matches_alsa_pro_input(mock_list_outputs):
    """Only alsa_input.*pro-input.*capture_AUX ports should be returned."""
    mock_list_outputs.return_value = [
        "alsa_input.usb-Focusrite_Scarlett_18i20_USB-00.pro-input-0:capture_AUX0",
        "alsa_input.usb-Focusrite_Scarlett_18i20_USB-00.pro-input-0:capture_AUX1",
        "Carla:audio-out1",
        "Firefox:input_FL",
    ]
    result = find_capture_input_ports()
    assert result == [
        "alsa_input.usb-Focusrite_Scarlett_18i20_USB-00.pro-input-0:capture_AUX0",
        "alsa_input.usb-Focusrite_Scarlett_18i20_USB-00.pro-input-0:capture_AUX1",
    ]


@patch("carla_mcp.utils.pw_link.pw_link_connect")
@patch("carla_mcp.utils.pw_link.pw_link_verify")
@patch("carla_mcp.utils.pw_link.find_monitor_output_ports")
def test_ensure_carla_to_monitors_creates_missing_connections(
    mock_find, mock_verify, mock_connect
):
    """out1 already connected, out2 needs connecting."""
    mock_find.return_value = [
        "alsa_output.usb-Focusrite_Scarlett_18i20_USB-00.pro-output-0:playback_AUX0",
        "alsa_output.usb-Focusrite_Scarlett_18i20_USB-00.pro-output-0:playback_AUX1",
    ]
    # out1 already connected, out2 not
    mock_verify.side_effect = [True, False]
    mock_connect.return_value = PwLinkResult(success=True)

    result = ensure_carla_to_monitors("Carla")
    assert result["connected"] == 1
    assert result["already_connected"] == 1
    assert result["failed"] == 0
    assert len(result["monitor_ports"]) == 2
    mock_connect.assert_called_once_with(
        "Carla:audio-out2",
        "alsa_output.usb-Focusrite_Scarlett_18i20_USB-00.pro-output-0:playback_AUX1",
    )


@patch("carla_mcp.utils.pw_link.find_monitor_output_ports")
def test_ensure_carla_to_monitors_no_monitors_found(mock_find):
    """Empty find returns all zeros."""
    mock_find.return_value = []
    result = ensure_carla_to_monitors("Carla")
    assert result["connected"] == 0
    assert result["already_connected"] == 0
    assert result["failed"] == 0
    assert result["monitor_ports"] == []
