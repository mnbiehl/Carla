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
            self.disconnect(src_l, dst_l)  # rollback left channel
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

    def list_connections(self, filter_prefixes: List[str] = None) -> List[Tuple[str, str]]:
        """List active connections. Parses pw-link -l output format.

        pw-link -l output looks like:
            PortName:output
              |-> DestName:input
            PortName2:output
              |-> DestName2:input
        """
        result = self._run_pw_link("-o", "-l")
        if result.returncode != 0:
            return []
        connections = []
        current_output = None
        for line in result.stdout.strip().split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if "|-> " in stripped:
                # This is a connection from current_output to a destination
                dest = stripped.split("|-> ", 1)[1].strip()
                if current_output:
                    src, dst = current_output, dest
                    if filter_prefixes:
                        if not any(
                            src.startswith(p) or dst.startswith(p)
                            for p in filter_prefixes
                        ):
                            continue
                    connections.append((src, dst))
            elif "|<- " not in stripped:
                # This is a port name (not an incoming connection line)
                current_output = stripped
        return connections

    def disconnect_client_from_system(self, client_name: str) -> int:
        """Disconnect all connections between a client and system I/O.

        Removes auto-connections PipeWire makes to hardware ports.
        Returns the number of connections disconnected.
        """
        all_conns = self.list_connections()
        count = 0
        for src, dst in all_conns:
            src_is_client = src.startswith(f"{client_name}:")
            dst_is_client = dst.startswith(f"{client_name}:")
            src_is_system = src.startswith("alsa_") or src.startswith("system:")
            dst_is_system = dst.startswith("alsa_") or dst.startswith("system:")

            if (src_is_client and dst_is_system) or (src_is_system and dst_is_client):
                self.disconnect(src, dst)
                count += 1
        return count
