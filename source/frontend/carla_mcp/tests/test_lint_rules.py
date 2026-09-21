import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "python_rules", Path(__file__).resolve().parents[4] / "linters" / "python_rules.py")
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)


def test_bare_except_flagged():
    out = rules.check_text("carla_mcp/bridge/x.py", "try:\n    pass\nexcept:\n    pass\n")
    assert len(out) == 1 and "no-bare-except" in out[0] and out[0].startswith("carla_mcp/bridge/x.py:3:")


def test_bare_except_flagged_inline_body():
    # `except:` with the body inline on the same line is still a bare except.
    out = rules.check_text("carla_mcp/bridge/x.py", "try:\n    pass\nexcept: pass\n")
    assert len(out) == 1 and "no-bare-except" in out[0] and out[0].startswith("carla_mcp/bridge/x.py:3:")


def test_broad_except_flagged_outside_allowlist_only():
    src = "try:\n    pass\nexcept Exception as e:\n    pass\n"
    assert rules.check_text("carla_mcp/bridge/tools/lifecycle.py", src)
    assert rules.check_text("carla_mcp/backends/rpc.py", src) == []
    assert rules.check_text("carla_mcp/bridge/result.py", src) == []
    assert rules.check_text("carla_mcp/worker/server.py", src) == []


def test_broad_except_tuple_form_flagged_regardless_of_position():
    exception_first = "try:\n    pass\nexcept (Exception, ValueError):\n    pass\n"
    exception_last = "try:\n    pass\nexcept (ValueError, Exception):\n    pass\n"
    assert rules.check_text("carla_mcp/bridge/x.py", exception_first)
    assert rules.check_text("carla_mcp/bridge/x.py", exception_last)


def test_allowlist_is_segment_aware():
    src = "try:\n    pass\nexcept Exception as e:\n    pass\n"
    # Shares a text tail with an allowlisted entry but crosses no real path
    # segment boundary, so it must NOT be exempt.
    assert rules.check_text("carla_mcp/notbridge/result.py", src)
    assert rules.check_text("carla_mcp/fake_backends/rpc.py", src)
    # Genuine segment match, with and without a leading path, IS exempt.
    assert rules.check_text("/abs/path/source/frontend/carla_mcp/bridge/result.py", src) == []
    assert rules.check_text("source/frontend/carla_mcp/bridge/result.py", src) == []


def test_skip_needs_reason():
    assert rules.check_text("t.py", "def test_x():\n    pytest.skip('x')\n")
    assert rules.check_text("t.py", "def test_x():\n    pytest.skip('x', reason='no jack')\n") == []
    assert rules.check_text("t.py", "@pytest.mark.skip()\ndef test_x():\n    pass\n")
    assert rules.check_text("t.py", "@pytest.mark.skip(reason='no jack')\ndef test_x():\n    pass\n") == []


def test_skip_bare_decorator_flagged():
    # `@pytest.mark.skip` with no call at all can never carry reason=.
    out = rules.check_text("t.py", "@pytest.mark.skip\ndef test_x():\n    pass\n")
    assert len(out) == 1 and "skip-needs-reason" in out[0] and out[0].startswith("t.py:1:")


def test_no_findings_inside_docstring_or_string():
    src = (
        '"""\n'
        'Example:\n'
        '    try:\n'
        '        pass\n'
        '    except:\n'
        '        pass\n'
        '"""\n'
        "s = 'pytest.skip(\\'x\\')'\n"
        "x = 1\n"
    )
    assert rules.check_text("t.py", src) == []


def test_syntax_error_reported_not_silently_passed():
    out = rules.check_text("t.py", "def broken(:\n    pass\n")
    assert len(out) == 1 and out[0].startswith("t.py:1:") and "syntax-error" in out[0]


def test_main_exit_code(tmp_path):
    good = tmp_path / "ok.py"; good.write_text("x = 1\n")
    bad = tmp_path / "bad.py"; bad.write_text("try:\n  pass\nexcept:\n  pass\n")
    assert rules.main([str(good)]) == 0
    assert rules.main([str(bad)]) == 1


def test_windows_path_with_colons_does_not_crash():
    """Paths with colons (Windows-style) must not cause ValueError in sort."""
    out = rules.check_text(
        r"C:\Users\dev\bridge\x.py",
        "try:\n    pass\nexcept Exception as e:\n    pass\n")
    assert len(out) == 1 and "no-broad-except" in out[0]
    # Verify the path and line number are preserved in output.
    assert out[0].startswith(r"C:\Users\dev\bridge\x.py:3:")


def test_nested_tuple_broad_except_flagged():
    """Nested tuples like except ((ValueError, Exception), TypeError): must be flagged."""
    src = "try:\n    pass\nexcept ((ValueError, Exception), TypeError):\n    pass\n"
    out = rules.check_text("carla_mcp/bridge/x.py", src)
    assert len(out) == 1 and "no-broad-except" in out[0]
    assert out[0].startswith("carla_mcp/bridge/x.py:3:")
