"""JACK/PipeWire audio routing via pw-link CLI."""

import subprocess
import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    success: bool
    message: str = ""


class JackRouter:
    """Manages JACK audio connections via pw-link."""

    def _run_pw_link(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["pw-link", *args], capture_output=True, text=True, timeout=5
        )

    def connect(self, source: str, dest: str) -> RouteResult:
        result = self._run_pw_link(source, dest)
        if result.returncode != 0:
            msg = f"Failed to connect {source} -> {dest}: {result.stderr.strip()}"
            logger.error(msg)
            return RouteResult(success=False, message=msg)
        logger.info(f"Connected {source} -> {dest}")
        return RouteResult(success=True)

    def disconnect(self, source: str, dest: str) -> RouteResult:
        result = self._run_pw_link("-d", source, dest)
        if result.returncode != 0:
            msg = f"Failed to disconnect {source} -> {dest}: {result.stderr.strip()}"
            logger.error(msg)
            return RouteResult(success=False, message=msg)
        logger.info(f"Disconnected {source} -> {dest}")
        return RouteResult(success=True)

    def connect_stereo(
        self, src_l: str, src_r: str, dst_l: str, dst_r: str
    ) -> RouteResult:
        r1 = self.connect(src_l, dst_l)
        if not r1.success:
            return r1
        r2 = self.connect(src_r, dst_r)
        if not r2.success:
            return r2
        return RouteResult(success=True)

    def disconnect_stereo(
        self, src_l: str, src_r: str, dst_l: str, dst_r: str
    ) -> RouteResult:
        r1 = self.disconnect(src_l, dst_l)
        r2 = self.disconnect(src_r, dst_r)
        if not r1.success or not r2.success:
            return RouteResult(
                success=False, message=f"{r1.message} {r2.message}".strip()
            )
        return RouteResult(success=True)

    def list_connections(self) -> List[Tuple[str, str]]:
        result = self._run_pw_link("-l", "-I")
        if result.returncode != 0:
            return []
        connections = []
        for line in result.stdout.strip().split("\n"):
            if " -> " in line:
                parts = line.strip().split(" -> ", 1)
                if len(parts) == 2:
                    connections.append((parts[0].strip(), parts[1].strip()))
        return connections
