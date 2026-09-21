"""The single pw-link wrapper for the bridge.

Phase 1 re-exports the existing subprocess helpers from utils/pw_link.py and
adds the link parser that used to live in orchestration/jack_router.py.
Phase 4 inlines the helpers here and deletes both old modules.
"""

from __future__ import annotations

import subprocess
from typing import List, Optional, Tuple

from carla_mcp.utils.pw_link import (
    pw_link_connect,
    pw_link_disconnect,
    pw_link_list_inputs,
    pw_link_list_outputs,
)


def parse_pw_link_links(text: str) -> List[Tuple[str, str]]:
    """Parse `pw-link -o -l` output into (output_port, input_port) pairs."""
    links: List[Tuple[str, str]] = []
    current: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|-> " in line:
            if current is not None:
                links.append((current, line.split("|-> ", 1)[1].strip()))
        else:
            current = line
    return links


def list_links() -> List[Tuple[str, str]]:
    try:
        result = subprocess.run(
            ["pw-link", "-o", "-l"], capture_output=True, text=True, timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return parse_pw_link_links(result.stdout)


def list_outputs() -> List[str]:
    return list(pw_link_list_outputs())


def list_inputs() -> List[str]:
    return list(pw_link_list_inputs())


def connect(src: str, dst: str) -> Optional[str]:
    result = pw_link_connect(src, dst)
    return None if result.success else (result.message or "pw-link failed")


def disconnect(src: str, dst: str) -> Optional[str]:
    result = pw_link_disconnect(src, dst)
    return None if result.success else (result.message or "pw-link failed")
