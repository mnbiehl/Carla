import json
import pytest
from carla_mcp.mcp_stdio_bridge import _build_rig_manifest


def test_rig_manifest_structure():
    manifest = _build_rig_manifest(
        carla_running=True,
        looper_running=True,
        carla_session="my_carla_project.carxp",
        looper_session="my_looper_session.json",
    )
    assert manifest["version"] == 1
    assert manifest["backends"]["carla"]["running"] is True
    assert manifest["backends"]["looper"]["running"] is True
    assert manifest["backends"]["carla"]["session"] == "my_carla_project.carxp"
    assert manifest["backends"]["looper"]["session"] == "my_looper_session.json"


def test_rig_manifest_defaults():
    manifest = _build_rig_manifest(
        carla_running=False,
        looper_running=False,
    )
    assert manifest["version"] == 1
    assert manifest["backends"]["carla"]["running"] is False
    assert manifest["backends"]["carla"]["session"] == ""


def test_rig_manifest_v2_includes_routing():
    manifest = _build_rig_manifest(
        carla_running=True, looper_running=True,
        routing=[
            {"src": "loopers:loop0_out_l", "dst": "Carla:audio-in3"},
            {"src": "Carla:audio-out1", "dst": "alsa_output.test:playback_AUX0"},
        ],
    )
    assert manifest["version"] == 2
    assert len(manifest["routing"]) == 2
    assert manifest["routing"][0]["src"] == "loopers:loop0_out_l"


def test_rig_manifest_v2_empty_routing():
    manifest = _build_rig_manifest(
        carla_running=True, looper_running=True, routing=[],
    )
    assert manifest["version"] == 2
    assert manifest["routing"] == []


def test_rig_manifest_v1_compat_no_routing():
    manifest = _build_rig_manifest(carla_running=True, looper_running=True)
    assert manifest["version"] == 1
    assert "routing" not in manifest
