#!/usr/bin/env python3
# linters/python_rules.py
"""Python lint rules for the new carla_mcp packages (agent-readable output).

Usage: python3 linters/python_rules.py <files or dirs...>
Exit 0 when clean, 1 when any finding.  Messages: path:line: rule: what — fix: how.

AST-based: rules look at parsed syntax, not raw lines, so matches inside
string/docstring literals never produce findings, and a file that fails to
parse is reported as a single syntax-error finding rather than skipped.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Optional

BROAD_EXCEPT_ALLOWLIST = (
    "backends/rpc.py", "backends/legacy_sse.py", "bridge/result.py",
    "worker/server.py", "rig/observe.py",
)

_BROAD_NAMES = ("Exception", "BaseException")


def _is_allowlisted(path: str) -> bool:
    # Segment-aware: exempt only on a real path-segment match, so
    # "notbridge/result.py" / "fake_backends/rpc.py" are NOT exempt while
    # ".../bridge/result.py" is.
    norm = path.replace("\\", "/")
    return any(norm == entry or norm.endswith("/" + entry) for entry in BROAD_EXCEPT_ALLOWLIST)


def _final_name(node: ast.expr) -> Optional[str]:
    """The bare name of a `Name`, or the trailing attribute of an `Attribute` chain."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_broad(node: ast.expr) -> bool:
    if _final_name(node) in _BROAD_NAMES:
        return True
    # Recurse into nested tuples (e.g., except ((ValueError, Exception), TypeError):)
    if isinstance(node, ast.Tuple):
        return any(_is_broad(elt) for elt in node.elts)
    return False


def _handler_is_broad(handler_type: ast.expr) -> bool:
    return _is_broad(handler_type)


def _is_pytest_skip_attr(node: ast.expr) -> bool:
    """True for the attribute-access chains `pytest.skip` or `pytest.mark.skip`."""
    if not isinstance(node, ast.Attribute) or node.attr != "skip":
        return False
    value = node.value
    if isinstance(value, ast.Name) and value.id == "pytest":
        return True  # pytest.skip
    return (isinstance(value, ast.Attribute) and value.attr == "mark"
            and isinstance(value.value, ast.Name) and value.value.id == "pytest")  # pytest.mark.skip


def check_text(path: str, text: str) -> List[str]:
    # Collect (lineno, message) pairs to avoid parsing line numbers from strings.
    findings_with_lineno: List[tuple[int, str]] = []
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        line = exc.lineno or 1
        return [f"{path}:{line}: syntax-error: {exc.msg} — fix: make the file valid Python"]

    allow_broad = _is_allowlisted(path)

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings_with_lineno.append((
                    node.lineno,
                    f"{path}:{node.lineno}: no-bare-except: bare `except:` swallows everything "
                    "— fix: catch a specific exception or raise ToolError/RpcError"))
            elif not allow_broad and _handler_is_broad(node.type):
                findings_with_lineno.append((
                    node.lineno,
                    f"{path}:{node.lineno}: no-broad-except: `except Exception` outside the RPC/tool "
                    "boundary — fix: let RpcError propagate to tool_boundary, or catch the specific type"))
        elif isinstance(node, ast.Call) and _is_pytest_skip_attr(node.func):
            if not any(kw.arg == "reason" for kw in node.keywords):
                findings_with_lineno.append((
                    node.lineno,
                    f"{path}:{node.lineno}: skip-needs-reason: skip without reason= "
                    "— fix: pytest.mark.skip(reason='...') so the skip self-documents"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                # A bare `@pytest.mark.skip` (no call) can never carry reason=.
                if _is_pytest_skip_attr(dec):
                    findings_with_lineno.append((
                        dec.lineno,
                        f"{path}:{dec.lineno}: skip-needs-reason: skip without reason= "
                        "— fix: pytest.mark.skip(reason='...') so the skip self-documents"))

    # Sort by line number, then return formatted strings.
    findings_with_lineno.sort(key=lambda x: x[0])
    return [msg for _, msg in findings_with_lineno]


def _files(args: List[str]) -> List[Path]:
    out: List[Path] = []
    for a in args:
        p = Path(a)
        out.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    return out


def main(argv: List[str]) -> int:
    findings: List[str] = []
    for f in _files(argv):
        findings.extend(check_text(str(f), f.read_text(errors="replace")))
    for line in findings:
        print(line)
    print(f"python_rules: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
