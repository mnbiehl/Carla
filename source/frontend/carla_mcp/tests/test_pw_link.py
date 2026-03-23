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
