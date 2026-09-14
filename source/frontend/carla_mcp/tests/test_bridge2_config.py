from pathlib import Path

from carla_mcp.bridge.config import BridgeConfig


def test_defaults_when_env_empty(tmp_path):
    cfg = BridgeConfig.from_env(env={"HOME": str(tmp_path)})
    assert cfg.carla_python == "/usr/bin/python3"
    assert cfg.looper_port == 8088
    assert cfg.carla_rpc_port == 8089
    assert cfg.session_dir == tmp_path / ".config" / "rig-sessions"
    assert cfg.log_dir == tmp_path / ".local" / "state" / "carla-mcp"
    assert cfg.frontend_dir.name == "frontend"
    assert cfg.carla_sse_url == "http://127.0.0.1:3001/sse"
    assert cfg.autosave_before_destructive is False


def test_env_overrides(tmp_path):
    env = {
        "HOME": str(tmp_path),
        "CARLA_PYTHON_PATH": "/opt/py/bin/python3",
        "LOOPERS_PATH": "/opt/loopers",
        "LOOPER_JSON_PORT": "9001",
        "CARLA_RPC_PORT": "9002",
        "RIG_SESSION_DIR": str(tmp_path / "sessions"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "CARLA_MCP_AUTOSAVE_BEFORE_DESTRUCTIVE": "1",
    }
    cfg = BridgeConfig.from_env(env=env)
    assert cfg.carla_python == "/opt/py/bin/python3"
    assert cfg.loopers_path == "/opt/loopers"
    assert cfg.looper_port == 9001
    assert cfg.carla_rpc_port == 9002
    assert cfg.session_dir == tmp_path / "sessions"
    assert cfg.log_dir == tmp_path / "state" / "carla-mcp"
    assert cfg.autosave_before_destructive is True


def test_package_init_has_no_eager_imports():
    import importlib, sys
    for name in list(sys.modules):
        if name.startswith("carla_mcp.main"):
            del sys.modules[name]
    importlib.import_module("carla_mcp")
    assert "carla_mcp.main" not in sys.modules
