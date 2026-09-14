import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "python_rules", Path(__file__).resolve().parents[4] / "linters" / "python_rules.py")
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)


def test_bare_except_flagged():
    out = rules.check_text("carla_mcp/bridge/x.py", "try:\n    pass\nexcept:\n    pass\n")
    assert len(out) == 1 and "no-bare-except" in out[0] and out[0].startswith("carla_mcp/bridge/x.py:3:")


def test_broad_except_flagged_outside_allowlist_only():
    src = "try:\n    pass\nexcept Exception as e:\n    pass\n"
    assert rules.check_text("carla_mcp/bridge/tools/lifecycle.py", src)
    assert rules.check_text("carla_mcp/backends/rpc.py", src) == []
    assert rules.check_text("carla_mcp/bridge/result.py", src) == []
    assert rules.check_text("carla_mcp/worker/server.py", src) == []


def test_skip_needs_reason():
    assert rules.check_text("t.py", "@pytest.mark.skip()\n")
    assert rules.check_text("t.py", "@pytest.mark.skip(reason='no jack')\n") == []
    assert rules.check_text("t.py", "pytest.skip('x')\n")


def test_main_exit_code(tmp_path):
    good = tmp_path / "ok.py"; good.write_text("x = 1\n")
    bad = tmp_path / "bad.py"; bad.write_text("try:\n  pass\nexcept:\n  pass\n")
    assert rules.main([str(good)]) == 0
    assert rules.main([str(bad)]) == 1
