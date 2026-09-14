#!/usr/bin/env python3
"""Python lint rules for the new carla_mcp packages (agent-readable output).

Usage: python3 linters/python_rules.py <files or dirs...>
Exit 0 when clean, 1 when any finding.  Messages: path:line: rule: what — fix: how.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

BROAD_EXCEPT_ALLOWLIST = (
    "backends/rpc.py", "backends/legacy_sse.py", "bridge/result.py",
    "worker/server.py", "rig/observe.py",
)
_BARE = re.compile(r"^\s*except\s*:\s*(#.*)?$")
_BROAD = re.compile(r"^\s*except\s+\(?\s*(Exception|BaseException)\b")
_SKIP = re.compile(r"pytest\.(mark\.)?skip\(")


def check_text(path: str, text: str) -> List[str]:
    findings: List[str] = []
    allow_broad = any(path.replace("\\", "/").endswith(a) for a in BROAD_EXCEPT_ALLOWLIST)
    for n, line in enumerate(text.splitlines(), start=1):
        if _BARE.match(line):
            findings.append(f"{path}:{n}: no-bare-except: bare `except:` swallows everything "
                            "— fix: catch a specific exception or raise ToolError/RpcError")
        elif _BROAD.match(line) and not allow_broad:
            findings.append(f"{path}:{n}: no-broad-except: `except Exception` outside the RPC/tool "
                            "boundary — fix: let RpcError propagate to tool_boundary, or catch the specific type")
        if _SKIP.search(line) and "reason=" not in line:
            findings.append(f"{path}:{n}: skip-needs-reason: skip without reason= "
                            "— fix: pytest.mark.skip(reason='...') so the skip self-documents")
    return findings


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
