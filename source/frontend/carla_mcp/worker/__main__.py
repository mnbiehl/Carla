"""Headless Carla worker: `python -m carla_mcp.worker --client-name NAME --port N`.

Runs an engine with no GUI and serves the worker RPC until `engine_stop`.
Started by the bridge for each track (phase 2).  Must run under the system
Python that can load libcarla_standalone2.so (CARLA_PYTHON_PATH).
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2]
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from carla_backend import (  # noqa: E402
    CarlaHostDLL,
    charPtrToString,
    ENGINE_OPTION_PATH_BINARIES,
    ENGINE_OPTION_PATH_RESOURCES,
    ENGINE_OPTION_PROCESS_MODE,
    ENGINE_PROCESS_MODE_PATCHBAY,
)

from carla_mcp.worker import attach, detach  # noqa: E402

IDLE_SLEEP_S = 0.0333  # Carla's own no-gui loop idles at 30 Hz
DEFAULT_BIN_DIR = _FRONTEND.parents[1] / "bin"


def build_host(bin_dir: Path):
    """Load libcarla_standalone2.so and point it at the binaries/resources."""
    host = CarlaHostDLL(str(bin_dir / "libcarla_standalone2.so"), False)
    host.set_engine_option(ENGINE_OPTION_PATH_BINARIES, 0, str(bin_dir))
    host.set_engine_option(ENGINE_OPTION_PATH_RESOURCES, 0, str(bin_dir / "resources"))
    host.set_engine_option(ENGINE_OPTION_PROCESS_MODE, ENGINE_PROCESS_MODE_PATCHBAY, "")
    return host


def idle_loop(server, host, stop_event: threading.Event) -> None:
    """Pump engine_idle() until engine_stop is requested or the engine dies."""
    while not stop_event.is_set() and host.is_engine_running():
        host.engine_idle()
        time.sleep(IDLE_SLEEP_S)


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="carla_mcp.worker")
    parser.add_argument("--client-name", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--driver", default="JACK")
    parser.add_argument("--bin-dir", default=os.getenv("CARLA_BIN_DIR", str(DEFAULT_BIN_DIR)))
    args = parser.parse_args(argv)

    host = build_host(Path(args.bin_dir))
    stop_event = threading.Event()
    server = attach(host, port=args.port, client_name=args.client_name,
                    version=os.getenv("CARLA_MCP_VERSION", "dev"),
                    on_engine_stop=stop_event.set)
    from carla_mcp.worker import events
    host.set_engine_callback(
        lambda h, action, pid, v1, v2, v3, vf, s: events.dispatch(
            action, pid, v1, v2, v3, vf, charPtrToString(s)))
    if not host.engine_init(args.driver, args.client_name):
        print(f"engine_init failed: {host.get_last_error()}", file=sys.stderr)
        detach(server)
        return 2
    print(f"worker {args.client_name} ready on port {server.port}", flush=True)
    try:
        idle_loop(server, host, stop_event)
    finally:
        host.engine_close()
        detach(server)
    return 0


if __name__ == "__main__":
    sys.exit(run())
