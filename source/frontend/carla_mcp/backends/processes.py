"""Child-process bookkeeping for the bridge (Carla GUI, track workers, loopers, a2j)."""

from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class UnitSpec:
    name: str
    argv: List[str]
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None


@dataclass
class _Running:
    spec: UnitSpec
    proc: subprocess.Popen
    log: object = field(repr=False)


class ProcessManager:
    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self._units: Dict[str, _Running] = {}

    def _log_path(self, name: str) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self.log_dir / f"{name}.log"

    def spawn(self, spec: UnitSpec) -> int:
        if self.is_running(spec.name):
            return self._units[spec.name].proc.pid
        log = open(self._log_path(spec.name), "a")
        try:
            proc = subprocess.Popen(spec.argv, cwd=spec.cwd, env=spec.env, stdout=log, stderr=log)
        except OSError:
            log.close()
            raise
        self._units[spec.name] = _Running(spec=spec, proc=proc, log=log)
        return proc.pid

    def _live(self, name: str) -> Optional[_Running]:
        unit = self._units.get(name)
        if unit is None:
            return None
        if unit.proc.poll() is not None:
            unit.log.close()
            del self._units[name]
            return None
        return unit

    def is_running(self, name: str) -> bool:
        return self._live(name) is not None

    def pid(self, name: str) -> Optional[int]:
        unit = self._live(name)
        return unit.proc.pid if unit else None

    def names(self) -> List[str]:
        return [n for n in list(self._units) if self._live(n) is not None]

    def stop(self, name: str, timeout: float = 5.0) -> Optional[str]:
        unit = self._live(name)
        if unit is None:
            return None
        unit.proc.terminate()
        try:
            unit.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            unit.proc.kill()
            unit.proc.wait()
        unit.log.close()
        del self._units[name]
        return None


def tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def a2j_running() -> bool:
    try:
        return subprocess.run(["pgrep", "-x", "a2jmidid"], capture_output=True, timeout=3).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ports_present(prefix: str, list_outputs: Callable[[], List[str]]) -> bool:
    return any(p.startswith(prefix) for p in list_outputs())
