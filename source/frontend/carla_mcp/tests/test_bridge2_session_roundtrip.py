"""In-process integration: session_save then session_load through the real
BridgeOps, do_save/do_load, CarlaClient, LooperClient and the decision-16
save wait. Nothing is patched at the do_save/do_load level.

Every server here is created by the test on an ephemeral port (port 0):
- a fake Carla worker: the real worker RpcServer + WorkerApi over a fake host;
- a fake loopers engine speaking the JSON-lines remote protocol.
pw-link, the legacy SSE shim and the process probes are in-memory fakes, so
nothing touches PipeWire, real processes, 8088/8089/3001 or ~/.config.
"""

import asyncio
import copy
import json
import socketserver
import threading
import time
from pathlib import Path
from unittest.mock import patch

from carla_mcp.bridge.app import Bridge
from carla_mcp.bridge.tools import sessions
from carla_mcp.rig.reconcile import LOOPER_MIDI_IN
from carla_mcp.worker.api import WorkerApi
from carla_mcp.worker.patchbay import PatchbayCache
from carla_mcp.worker.server import RpcServer

SAVE_DELAY_S = 0.3  # the looper acks SaveSessionAt before project.loopers lands


class FakeCarlaHost:
    """The slice of the Carla host API the worker's project verbs use."""

    def __init__(self):
        self.saved = []
        self.loaded = []

    def save_project(self, path):
        Path(path).write_text("<?xml version='1.0'?><CARLA-PROJECT/>")
        self.saved.append(path)
        return True

    def load_project(self, path):
        self.loaded.append(path)
        return Path(path).exists()

    def get_last_error(self):
        return "fake host error"


class FakeLooper:
    """loopers' JSON-lines remote: GetState, SaveSessionAt (async write), LoadSession, mutes."""

    def __init__(self):
        self.commands = []
        self.writers = []
        self.state = {
            "loopers": [{"id": 7, "name": "uke", "port_index": 0, "mode": "Playing",
                         "level_db": -3.0, "pan": 0.0, "input_source": None}],
            "main_muted": False,
            "all_muted": True,
        }
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    if line.strip():
                        reply = outer.handle(json.loads(line))
                        self.wfile.write(json.dumps(reply).encode() + b"\n")
                        self.wfile.flush()

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        for w in self.writers:
            w.join(timeout=2)

    def _write_project(self, dir_path):
        time.sleep(SAVE_DELAY_S)
        d = Path(dir_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.loopers").write_text(json.dumps(
            {"save_time": int(time.time() * 1000), "loopers": self.state["loopers"]}))

    def handle(self, cmd):
        self.commands.append(cmd)
        if cmd == "GetState":
            return {"state": copy.deepcopy(self.state)}
        if isinstance(cmd, dict) and "SaveSessionAt" in cmd:
            w = threading.Thread(target=self._write_project, args=(cmd["SaveSessionAt"],), daemon=True)
            self.writers.append(w)
            w.start()
            return {"ok": True}
        if isinstance(cmd, dict) and ("LoadSession" in cmd or "SetMainOutputMute" in cmd
                                      or "SetAllOutputsMute" in cmd):
            return {"ok": True}
        return {"error": f"fake looper: unsupported command {cmd!r}"}

    def of(self, key):
        return [c[key] for c in self.commands if isinstance(c, dict) and key in c]


class FakePipeWire:
    OUTPUTS = ["loopers:loop0_out_l", "loopers:loop0_out_r", "Carla:audio-out1", "Carla:audio-out2"]
    INPUTS = ["loopers:loop0_in_l", "loopers:loop0_in_r", "Carla:audio-in1", "Carla:audio-in2",
              LOOPER_MIDI_IN]

    def __init__(self, links):
        self.links = set(links)
        self.connected = []
        self.disconnected = []

    def list_links(self):
        return sorted(self.links)

    def list_outputs(self):
        return list(self.OUTPUTS)

    def list_inputs(self):
        return list(self.INPUTS)

    def connect(self, src, dst):
        self.links.add((src, dst))
        self.connected.append((src, dst))
        return None

    def disconnect(self, src, dst):
        self.links.discard((src, dst))
        self.disconnected.append((src, dst))
        return None


WIRED = {("loopers:loop0_out_l", "Carla:audio-in1"), ("loopers:loop0_out_r", "Carla:audio-in2")}


def test_session_save_then_load_round_trip_through_real_bridge_ops(tmp_path):
    started = time.monotonic()
    host = FakeCarlaHost()
    worker = RpcServer(WorkerApi(host, PatchbayCache(), version="fake-worker"), port=0)
    looper = FakeLooper()
    pw = FakePipeWire(WIRED)
    sse_calls = []

    async def fake_legacy_sse(url, name, args, timeout=None):
        sse_calls.append((name, args))
        if name == "export_rig_state":
            return {"version": 1, "nodes": [], "edges": []}
        if name == "rig_handles":
            return {"nodes": {}}
        if name == "import_rig_state":
            return {"messages": []}
        raise AssertionError(f"unexpected legacy SSE call {name}")

    worker.start()
    looper.start()
    try:
        b = Bridge.for_tests(tmp_dir=str(tmp_path), legacy_sse=fake_legacy_sse, env={
            "CARLA_RPC_PORT": str(worker.port),
            "LOOPER_JSON_PORT": str(looper.port),
            "RIG_SESSION_DIR": str(tmp_path / "sessions"),
        })
        tools = {t.name: t for t in sessions.build(b)}
        sdir = b.config.session_dir / "roundtrip"

        def no_spawn(spec):
            raise AssertionError(f"round trip must not spawn {spec.name}")

        with patch("carla_mcp.backends.pw_link.list_links", side_effect=pw.list_links), \
             patch("carla_mcp.backends.pw_link.list_outputs", side_effect=pw.list_outputs), \
             patch("carla_mcp.backends.pw_link.list_inputs", side_effect=pw.list_inputs), \
             patch("carla_mcp.backends.pw_link.connect", side_effect=pw.connect), \
             patch("carla_mcp.backends.pw_link.disconnect", side_effect=pw.disconnect), \
             patch("carla_mcp.bridge.ops.a2j_running", return_value=True), \
             patch("carla_mcp.bridge.units.a2j_running", return_value=True), \
             patch("carla_mcp.bridge.units.carla_gui_running", return_value=False), \
             patch.object(b.processes, "spawn", side_effect=no_spawn):

            # ----- save -----------------------------------------------------
            saved = asyncio.run(tools["session_save"].fn("roundtrip"))
            assert saved["ok"] is True, saved
            save_report = saved["result"]["report"]
            assert save_report.splitlines()[0] == "OK", save_report
            assert (sdir / "rig_session.json").is_file()
            assert (sdir / "looper" / "project.loopers").is_file()
            assert (sdir / "carla_project.carxp").is_file()
            assert host.saved == [str(sdir / "carla_project.carxp")]
            assert looper.of("SaveSessionAt") == [str(sdir / "looper")]
            assert ("export_rig_state", {"chains_dir": str(sdir / "chains")}) in sse_calls
            assert b.session_name == "roundtrip" and b.graph is not None
            saved_graph_nodes = set(b.graph.nodes)
            assert "loop:0" in saved_graph_nodes and "app:looper" in saved_graph_nodes

            # ----- live rig drifts, bridge forgets the session ------------------
            b.graph = None
            b.session_name = None
            pw.links = {("loopers:loop0_out_l", "Carla:audio-in2")}  # stale PipeWire-restored link

            # ----- load -----------------------------------------------------
            loaded = asyncio.run(tools["session_load"].fn("roundtrip"))
            assert loaded["ok"] is True, loaded
            load_report = loaded["result"]["report"]
            assert load_report.splitlines()[0] == "OK", load_report
            assert looper.of("LoadSession") == [str(sdir / "looper" / "project.loopers")]
            assert looper.of("SetAllOutputsMute") == [True] and looper.of("SetMainOutputMute") == [False]
            assert host.loaded == [str(sdir / "carla_project.carxp")]
            assert ("loopers:loop0_out_l", "Carla:audio-in2") in pw.disconnected
            assert pw.links == WIRED
            assert b.session_name == "roundtrip" and b.graph is not None
            assert set(b.graph.nodes) == saved_graph_nodes
            state = loaded["result"]["state"]
            assert state["session"] == "roundtrip" and state["versions"]["carla"] == "fake-worker"
            assert state["verdict"] == "OK", state
    finally:
        worker.stop()
        looper.stop()
    assert time.monotonic() - started < 5.0
