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
